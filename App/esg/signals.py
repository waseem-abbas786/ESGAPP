import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Document, ExtractedText, ESGScore, KeywordResult, ScoreBreakdown, Supplier
from .esg_logic import (
    extract_text_from_file,
    find_keywords_in_text,
    calculate_category_scores,
    calculate_total_score,
    determine_risk_level,
    ESG_KEYWORDS,
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Document)
def extract_text_from_document(sender, instance: Document, created: bool, **kwargs):
    if not created or not instance.file or not instance.file.name:
        return
    
    def run():
        try:
            logger.info(f"📄 Extracting text from Document {instance.pk} ({instance.file_format})")
            
            result = extract_text_from_file(instance.file.path, instance.file_format)
            
            ExtractedText.objects.update_or_create(
                document=instance,
                defaults={
                    'raw_text': result.text,
                    'extractor_lib': result.extractor,
                }
            )
            
            logger.info(
                f"✓ Text extracted for Document {instance.pk} "
                f"({len(result.text)} chars, extractor: {result.extractor})"
            )
            
        except Exception as e:
            logger.exception(f"✗ Text extraction failed for Document {instance.pk}: {e}")
    
    transaction.on_commit(run)


@receiver(post_save, sender=ExtractedText)
def process_keywords_and_calculate_score(sender, instance: ExtractedText, created: bool, **kwargs):
    if not instance.raw_text or not instance.raw_text.strip():
        logger.warning(f"Skipping: ExtractedText {instance.pk} has no text")
        return
    
    def run():
        try:
            supplier = instance.document.supplier
            logger.info(f"🔍 Processing keywords for Document {instance.document.pk} (Supplier: {supplier.name})")
            keyword_results = find_keywords_in_text(instance.raw_text)
            
            total_found = sum(
                sum(1 for _, found, _ in results if found) 
                for results in keyword_results.values()
            )
            logger.info(f"Found {total_found} keywords in this document")
            
    
            KeywordResult.objects.filter(extraction=instance).delete()
            
            keyword_objects = [
                KeywordResult(
                    extraction=instance,
                    esg_category=category,
                    keyword=keyword,
                    found=found,
                    points_awarded=points
                )
                for category, results in keyword_results.items()
                for keyword, found, points in results
            ]
            
            KeywordResult.objects.bulk_create(keyword_objects)
            logger.info(f"Saved {len(keyword_objects)} keyword results")
            recalculate_supplier_score(supplier)
            
        except Exception as e:
            logger.exception(f"✗ Keyword processing failed for ExtractedText {instance.pk}: {e}")
            raise
    
    transaction.on_commit(run)


@receiver(post_delete, sender=Document)
def recalculate_on_document_delete(sender, instance: Document, **kwargs):
    """
    When a document is deleted, recalculate supplier's score based on remaining documents.
    
    Triggers: Document deleted
    """
    def run():
        try:
            supplier = instance.supplier
            logger.info(f"🗑️ Document deleted for {supplier.name}, recalculating score")
            recalculate_supplier_score(supplier)
        except Exception as e:
            logger.exception(f"✗ Score recalculation failed after document delete: {e}")
    
    transaction.on_commit(run)


def recalculate_supplier_score(supplier: Supplier):
    try:
        logger.info(f"📊 Recalculating score for: {supplier.name}")
        processed_documents = Document.objects.filter(
            supplier=supplier,
            extraction__isnull=False 
        ).select_related('extraction')
        
        doc_count = processed_documents.count()
        logger.info(f"Found {doc_count} processed documents")
        
        if doc_count == 0:
            _set_zero_score(supplier)
            return
        
        aggregated_keywords = {
            'E': {kw: {'found': False, 'points': pts} for kw, pts in ESG_KEYWORDS['E'].items()},
            'S': {kw: {'found': False, 'points': pts} for kw, pts in ESG_KEYWORDS['S'].items()},
            'G': {kw: {'found': False, 'points': pts} for kw, pts in ESG_KEYWORDS['G'].items()},
        }
        for document in processed_documents:
            keywords = KeywordResult.objects.filter(extraction=document.extraction)
            
            for keyword_result in keywords:
                if keyword_result.found:
                    category = keyword_result.esg_category
                    keyword = keyword_result.keyword
                    aggregated_keywords[category][keyword]['found'] = True
    
        keyword_results = {
            category: [
                (keyword, data['found'], data['points'] if data['found'] else 0)
                for keyword, data in keywords.items()
            ]
            for category, keywords in aggregated_keywords.items()
        }
        
        category_scores = calculate_category_scores(keyword_results)
        total_score = calculate_total_score(category_scores)
        risk_level = determine_risk_level(total_score)
        total_keywords_found = sum(
            sum(1 for kw, data in aggregated_keywords[cat].items() if data['found'])
            for cat in ['E', 'S', 'G']
        )
        
        logger.info(
            f"Score: {total_score}/100, Risk: {risk_level}, "
            f"Keywords: {total_keywords_found}, Documents: {doc_count}"
        )
        esg_score, created = ESGScore.objects.update_or_create(
            supplier=supplier,
            defaults={
                'total_score': total_score,
                'risk_level': risk_level,
                'env_points': category_scores['E'],
                'social_points': category_scores['S'],
                'governance_points': category_scores['G'],
            }
        )
        
        logger.info(f"ESGScore {'created' if created else 'updated'}")
        ScoreBreakdown.objects.filter(score=esg_score).delete()
        
        breakdown_objects = []
        category_names = {'E': 'Environmental', 'S': 'Social', 'G': 'Governance'}
        
        for category, keywords in aggregated_keywords.items():
            for keyword, data in keywords.items():
                if data['found']:
                    breakdown_objects.append(
                        ScoreBreakdown(
                            score=esg_score,
                            factor_name=f"{category_names[category]} - {keyword.title()}",
                            max_points=data['points'],
                            earned_points=data['points'],
                            achieved=True
                        )
                    )
        
        ScoreBreakdown.objects.bulk_create(breakdown_objects)
        logger.info(f"Created {len(breakdown_objects)} breakdown entries")
        
        supplier.esg_score = total_score
        supplier.risk_level = risk_level
        supplier.save(update_fields=['esg_score', 'risk_level', 'updated_at'])
        
        logger.info(
            f"✓ {supplier.name}: Score={total_score}, Risk={risk_level}, "
            f"Keywords={total_keywords_found}, Docs={doc_count}"
        )
        
    except Exception as e:
        logger.exception(f"✗ Failed to recalculate score for {supplier.name}: {e}")
        raise


def _set_zero_score(supplier: Supplier):
    try:
        ESGScore.objects.update_or_create(
            supplier=supplier,
            defaults={
                'total_score': 0,
                'risk_level': 'HIGH',
                'env_points': 0,
                'social_points': 0,
                'governance_points': 0,
            }
        )
        
        ScoreBreakdown.objects.filter(score__supplier=supplier).delete()
        
        supplier.esg_score = 0
        supplier.risk_level = 'HIGH'
        supplier.save(update_fields=['esg_score', 'risk_level', 'updated_at'])
        
        logger.info(f"Set score to 0 for {supplier.name} (no documents)")
        
    except Exception as e:
        logger.exception(f"✗ Failed to set zero score for {supplier.name}: {e}")



def recalculate_all_suppliers():
    suppliers = Supplier.objects.all()
    total = suppliers.count()
    
    logger.info(f"🔄 Recalculating {total} suppliers...")
    
    for index, supplier in enumerate(suppliers, 1):
        logger.info(f"[{index}/{total}] {supplier.name}")
        recalculate_supplier_score(supplier)
    
    logger.info(f"✓ Recalculation complete for {total} suppliers")