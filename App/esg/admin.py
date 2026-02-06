from django.contrib import admin
from .models import Supplier, Document, ExtractedText, ESGScore, KeywordResult, ScoreBreakdown 

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "country",
        "category",
        "esg_score",
        "risk_level",
    )
    search_fields = ("name", "supplier_code", "user__username")
    list_filter = ("risk_level", "country", "category")

 
@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("supplier", "document_type", "file_format", "uploaded_at")

@admin.register(ESGScore)
class ESGScoreAdmin(admin.ModelAdmin):
    list_display = ("supplier", "total_score", "risk_level", "calculated_at")


@admin.register(ExtractedText)
class ExtractedTextAdmin(admin.ModelAdmin):
    list_display = ("document", "extractor_lib", "extracted_at")

@admin.register(KeywordResult)
class KeywordResultAdmin(admin.ModelAdmin):
    list_display = ("keyword", "esg_category", "found", "points_awarded")

@admin.register(ScoreBreakdown)
class ScoreBreakdownAdmin(admin.ModelAdmin):
    list_display = ("factor_name", "earned_points", "max_points", "achieved")

