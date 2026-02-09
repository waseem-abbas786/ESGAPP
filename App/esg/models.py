from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Supplier(models.Model):
    RISK_CHOICES = (
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='supplier',
        null=True,  
        blank=True,  
        help_text="Django user account for this supplier"
    )

    supplier_code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    country = models.CharField(max_length=80)
    category = models.CharField(max_length=60)

    esg_score = models.PositiveIntegerField(null=True, blank=True)
    risk_level = models.CharField(max_length=10, choices=RISK_CHOICES, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'


class Document(models.Model):
    DOCUMENT_TYPES = (
        ("policy", "Sustainability Policy"),
        ("iso", "ISO Certificate"),
        ("code", "Code of Conduct"),
        ("report", "ESG Report"),
        ("compliance", "Compliance Document"),
    )

    FORMATS = (
        ("PDF", "PDF"),
        ("DOCX", "DOCX"),
    )

    supplier = models.ForeignKey(
        Supplier, related_name="documents", on_delete=models.CASCADE
    )

    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to="documents/")
    file_format = models.CharField(max_length=10, choices=FORMATS)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.supplier.name} - {self.document_type}"


class ExtractedText(models.Model):
    document = models.OneToOneField(
        Document, related_name="extraction", on_delete=models.CASCADE
    )

    raw_text = models.TextField()
    extractor_lib = models.CharField(max_length=50)  
    extracted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Extraction for {self.document.id}"


class KeywordResult(models.Model):
    ESG_CATEGORIES = (
        ("E", "Environmental"),
        ("S", "Social"),
        ("G", "Governance"),
    )

    extraction = models.ForeignKey(
        ExtractedText, related_name="keywords", on_delete=models.CASCADE
    )

    esg_category = models.CharField(max_length=1, choices=ESG_CATEGORIES)
    keyword = models.CharField(max_length=80)
    found = models.BooleanField(default=False)
    points_awarded = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.keyword} ({self.esg_category})"

class ESGScore(models.Model):
    RISK_CHOICES = (
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    )

    supplier = models.OneToOneField(
        Supplier, related_name="score", on_delete=models.CASCADE
    )

    total_score = models.PositiveIntegerField()
    risk_level = models.CharField(max_length=10, choices=RISK_CHOICES)

    env_points = models.PositiveIntegerField(default=0)
    social_points = models.PositiveIntegerField(default=0)
    governance_points = models.PositiveIntegerField(default=0)

    calculated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.supplier.name} - {self.total_score}"

class ScoreBreakdown(models.Model):
    score = models.ForeignKey(
        ESGScore, related_name="breakdown", on_delete=models.CASCADE
    )

    factor_name = models.CharField(max_length=60)
    max_points = models.PositiveIntegerField()
    earned_points = models.PositiveIntegerField()
    achieved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.factor_name}: {self.earned_points}"


