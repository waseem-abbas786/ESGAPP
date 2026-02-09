import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import (
    Document, 
    ExtractedText, 
    KeywordResult, 
    ESGScore, 
    ScoreBreakdown,
)
from .text_extraction import extract_text_from_file
from .keyword_scoring import (
    find_keywords_in_text,
    calculate_category_scores,
    calculate_total_score,
    determine_risk_level,
    recalculate_supplier_score,
    ESG_KEYWORDS,
    recalculate_supplier_score,
)

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Document)
def extract_text_from_document(sender, instance: Document, created: bool, **kwargs):
    """Extract text from document when it's uploaded."""
    
    if not created or not instance.file or not instance.file.name:
        return
    
    def run():
        try:
            logger.info(f"Extracting text from Document {instance.pk}")
            
            result = extract_text_from_file(instance.file.path, instance.file_format)
            
            ExtractedText.objects.update_or_create(
                document=instance,
                defaults={
                    'raw_text': result.text,
                    'extractor_lib': result.extractor,
                }
            )
            
            logger.info(f"✓ Text extracted for Document {instance.pk}")
            
        except Exception as e:
            logger.exception(f"✗ Text extraction failed for Document {instance.pk}: {e}")
    
    transaction.on_commit(run)


@receiver(post_save, sender=ExtractedText)
def process_keywords_and_calculate_score(sender, instance: ExtractedText, created: bool, **kwargs):
    
    if not instance.raw_text or not instance.raw_text.strip():
        return
    
    def run():
        try:
            logger.info(f"Starting scoring for ExtractedText {instance.pk}")
            
            keyword_results = find_keywords_in_text(instance.raw_text)
            
            total_found = sum(
                sum(1 for _, found, _ in results if found) 
                for results in keyword_results.values()
            )
            logger.info(f"Found {total_found} keywords")
    
            KeywordResult.objects.filter(extraction=instance).delete()
            
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
            category_scores = calculate_category_scores(keyword_results)
            total_score = calculate_total_score(category_scores)
            risk_level = determine_risk_level(total_score)
            
            logger.info(f"Score: {total_score}/100, Risk: {risk_level}")
            
            supplier = instance.document.supplier
            
            esg_score, _ = ESGScore.objects.update_or_create(
                supplier=supplier,
                defaults={
                    'total_score': total_score,
                    'risk_level': risk_level,
                    'env_points': category_scores['E'],
                    'social_points': category_scores['S'],
                    'governance_points': category_scores['G'],
                }
            )
            
            ScoreBreakdown.objects.filter(score=esg_score).delete()
            
            breakdown_objects = []
            category_names = {'E': 'Environmental', 'S': 'Social', 'G': 'Governance'}
            
            for category, results in keyword_results.items():
                for keyword, found, points in results:
                    if found:
                        breakdown_objects.append(
                            ScoreBreakdown(
                                score=esg_score,
                                factor_name=f"{category_names[category]} - {keyword.title()}",
                                max_points=ESG_KEYWORDS[category][keyword],
                                earned_points=points,
                                achieved=True
                            )
                        )
            
            ScoreBreakdown.objects.bulk_create(breakdown_objects)
            
            supplier.esg_score = total_score
            supplier.risk_level = risk_level
            supplier.save(update_fields=['esg_score', 'risk_level', 'updated_at'])
            
            logger.info(
                f"✓ Scoring complete for {supplier.name}: "
                f"Score={total_score}, Risk={risk_level}, Keywords={total_found}"
            )
            
        except Exception as e:
            logger.exception(f"✗ Scoring failed for ExtractedText {instance.pk}: {e}")
            raise
    
    transaction.on_commit(run)

@receiver(post_delete, sender=ExtractedText)
def recalc_score_on_extracted_text_delete(sender, instance: ExtractedText, **kwargs):
    """Recalculate or remove ESG score when an ExtractedText is deleted."""
    
    supplier = instance.document.supplier

    def run():
        try:
            remaining_extractions = ExtractedText.objects.filter(document__supplier=supplier)
            
            if remaining_extractions.exists():
                logger.info(f"Recalculating ESG score for supplier {supplier.name} due to ExtractedText deletion")
                recalculate_supplier_score(supplier)
                logger.info(f"✓ ESG score recalculated for supplier {supplier.name}")
            else:
                logger.info(f"No remaining documents for supplier {supplier.name}. Deleting ESGScore and ScoreBreakdown")
                
                ESGScore.objects.filter(supplier=supplier).delete()
                ScoreBreakdown.objects.filter(score__supplier=supplier).delete()
                
                supplier.esg_score = None
                supplier.risk_level = None
                supplier.save(update_fields=['esg_score', 'risk_level', 'updated_at'])
                
                logger.info(f"✓ ESGScore removed for supplier {supplier.name}")
                
        except Exception as e:
            logger.exception(f"✗ Failed to update ESG score for supplier {supplier.name}: {e}")
            raise

    transaction.on_commit(run)
