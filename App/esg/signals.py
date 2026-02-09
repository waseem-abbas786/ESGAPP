import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Document, ExtractedText
from .text_extraction import extract_text_from_file

logger = logging.getLogger(__name__)
logger.warning("signals.py imported") 


@receiver(post_save, sender=Document)
def extract_and_persist_text(sender, instance: Document, created: bool, **kwargs):
    logger.warning("post_save fired: id=%s created=%s file=%s",
                   instance.pk, created, getattr(instance.file, "name", None))

    if not created:
        return

    if not instance.file or not instance.file.name:
        logger.warning("skip: missing file")
        return

    def run():
        try:
            logger.warning("on_commit start: id=%s path=%s fmt=%s",
                           instance.pk, instance.file.path, instance.file_format)
            res = extract_text_from_file(instance.file.path, instance.file_format)
            obj, _ = ExtractedText.objects.update_or_create(
                document=instance,
                defaults={"raw_text": res.text, "extractor_lib": res.extractor},
            )
            logger.warning("on_commit done: extracted_id=%s text_len=%s", obj.pk, len(res.text or ""))
        except Exception:
            logger.exception("on_commit failed: id=%s", instance.pk)

    transaction.on_commit(run)
