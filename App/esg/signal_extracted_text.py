import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ExtractedText, KeywordResult, ESGScore, ScoreBreakdown, AuditLog
from .keyword_scoring import (
    find_keywords_in_text,
    calculate_category_scores,
    calculate_total_score,
    determine_risk_level,
    ESG_KEYWORDS,
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ExtractedText)
def process_keywords_and_calculate_score(sender, instance: ExtractedText, created: bool, **kwargs):
 
    logger.info(f"ExtractedText post_save signal fired: id={instance.pk}, created={created}")

    if not instance.raw_text or not instance.raw_text.strip():
        logger.warning(f"Skipping processing: ExtractedText {instance.pk} has empty text")
        return
    
    def run():
        try:
            logger.info(f"Starting keyword processing for ExtractedText {instance.pk}")
            logger.info("Step 1: Finding keywords in text...")
            keyword_results = find_keywords_in_text(instance.raw_text)
            
            total_found = sum(
                sum(1 for _, found, _ in results if found) 
                for results in keyword_results.values()
            )
            logger.info(f"Found {total_found} keywords in text")
            
            logger.info("Step 2: Saving keyword results to database...")
            
            KeywordResult.objects.filter(extraction=instance).delete()
            logger.info(f"Deleted old keyword results for extraction {instance.pk}")
            
            keyword_objects = []
            
            for category, results in keyword_results.items():
                for keyword, found, points in results:
                    keyword_objects.append(
                        KeywordResult(
                            extraction=instance,
                            esg_category=category,
                            keyword=keyword,
                            found=found,
                            points_awarded=points
                        )
                    )
            
            KeywordResult.objects.bulk_create(keyword_objects)
            logger.info(f"Created {len(keyword_objects)} keyword results")
            
            logger.info("Step 3: Calculating category scores...")
            category_scores = calculate_category_scores(keyword_results)
            
            logger.info(f"Environmental points: {category_scores['E']}")
            logger.info(f"Social points: {category_scores['S']}")
            logger.info(f"Governance points: {category_scores['G']}")
            
            logger.info("Step 4: Calculating total score...")
            total_score = calculate_total_score(category_scores)
            logger.info(f"Total ESG score: {total_score}/100")
            
            logger.info("Step 5: Determining risk level...")
            risk_level = determine_risk_level(total_score)
            logger.info(f"Risk level: {risk_level}")
            
            supplier = instance.document.supplier
            logger.info(f"Processing for supplier: {supplier.name} (ID: {supplier.pk})")
            
            logger.info("Step 6: Saving ESG score to database...")
            
            esg_score, score_created = ESGScore.objects.update_or_create(
                supplier=supplier,
                defaults={
                    'total_score': total_score,
                    'risk_level': risk_level,
                    'env_points': category_scores['E'],
                    'social_points': category_scores['S'],
                    'governance_points': category_scores['G'],
                }
            )
            
            action = "Created" if score_created else "Updated"
            logger.info(f"{action} ESGScore (ID: {esg_score.pk}) for supplier {supplier.name}")
            
            logger.info("Step 7: Creating score breakdown...")
            
   
            ScoreBreakdown.objects.filter(score=esg_score).delete()
            
            breakdown_objects = []
            
            for category, results in keyword_results.items():
                category_name = {
                    'E': 'Environmental',
                    'S': 'Social',
                    'G': 'Governance'
                }[category]
                
                for keyword, found, points in results:
                    if found:  
                        max_points = ESG_KEYWORDS[category][keyword]
                        breakdown_objects.append(
                            ScoreBreakdown(
                                score=esg_score,
                                factor_name=f"{category_name} - {keyword.title()}",
                                max_points=max_points,
                                earned_points=points,
                                achieved=True
                            )
                        )
            
            ScoreBreakdown.objects.bulk_create(breakdown_objects)
            logger.info(f"Created {len(breakdown_objects)} score breakdown items")
            
            logger.info("Step 8: Updating supplier risk level...")
            
            supplier.esg_score = total_score
            supplier.risk_level = risk_level
            supplier.save(update_fields=['esg_score', 'risk_level', 'updated_at'])
            
            logger.info(f"Updated supplier {supplier.name}: score={total_score}, risk={risk_level}")
            
            logger.info("Step 9: Updating dashboard cache...")
            
            from .models import DashboardCache
            
            cache, cache_created = DashboardCache.objects.update_or_create(
                supplier=supplier,
                defaults={
                    'cached_score': total_score,
                    'cached_risk': risk_level,
                }
            )
            
            cache_action = "Created" if cache_created else "Updated"
            logger.info(f"{cache_action} dashboard cache for supplier {supplier.name}")
            
            logger.info("Step 10: Creating audit log...")
            
            AuditLog.objects.create(
                supplier=supplier,
                action='SCORE',
                entity_type=f'ESG Score Calculation - Document {instance.document.pk} - Total: {total_score}'
            )
            
            logger.info(f"Created audit log for supplier {supplier.name}")
            
            logger.info(
                f"✓ Successfully processed ExtractedText {instance.pk}: "
                f"Score={total_score}/100, Risk={risk_level}, "
                f"Keywords found={total_found}"
            )
            
        except Exception as e:
            logger.exception(
                f"✗ Failed to process ExtractedText {instance.pk}: {str(e)}"
            )
            raise
    
    transaction.on_commit(run)