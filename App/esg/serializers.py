from rest_framework import serializers
from .models import (
    Supplier, Document, ExtractedText, KeywordResult,
    ESGScore, ScoreBreakdown,
)


class DynamicFieldsSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        fields = kwargs.pop('fields', None)
        exclude = kwargs.pop('exclude', None)
        super().__init__(*args, **kwargs)
        
        if fields is not None:
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)
        
        if exclude is not None:
            for field_name in exclude:
                self.fields.pop(field_name, None)

class ScoreBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreBreakdown
        fields = ['id', 'factor_name', 'max_points', 'earned_points', 'achieved']
        read_only_fields = fields


class KeywordResultSerializer(serializers.ModelSerializer):
    esg_category_label = serializers.CharField(source='get_esg_category_display', read_only=True)
    
    class Meta:
        model = KeywordResult
        fields = ['id', 'esg_category', 'esg_category_label', 'keyword', 'found', 'points_awarded']
        read_only_fields = fields


class ExtractedTextSerializer(DynamicFieldsSerializer):
    keyword_results = serializers.SerializerMethodField()
    
    class Meta:
        model = ExtractedText
        fields = ['id', 'raw_text', 'extractor_lib', 'extracted_at', 'keyword_results']
        read_only_fields = fields
    
    def get_keyword_results(self, obj):
        if self.context.get('include_keywords', False):
            return KeywordResultSerializer(obj.keywords.all(), many=True).data
        return None


class ESGScoreSerializer(DynamicFieldsSerializer):
    risk_level_label = serializers.CharField(source='get_risk_level_display', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    breakdowns = serializers.SerializerMethodField()
    
    class Meta:
        model = ESGScore
        fields = [
            'id', 'supplier', 'supplier_name', 'total_score', 'risk_level', 'risk_level_label',
            'env_points', 'social_points', 'governance_points', 'calculated_at', 'breakdowns',
        ]
        read_only_fields = ['id', 'risk_level', 'calculated_at']
    
    def get_breakdowns(self, obj):
        if self.context.get('include_breakdowns', False):
            return ScoreBreakdownSerializer(obj.breakdown.all(), many=True).data
        return None
    
    def validate_total_score(self, value):
        if not (0 <= value <= 100):
            raise serializers.ValidationError("total_score must be between 0 and 100.")
        return value


def ESGScoreListSerializer(*args, **kwargs):
    return ESGScoreSerializer(
        *args,
        fields=['id', 'supplier_name', 'total_score', 'risk_level', 'risk_level_label',
                'env_points', 'social_points', 'governance_points', 'calculated_at'],
        **kwargs
    )


def ESGScoreDetailSerializer(*args, **kwargs):
    kwargs['context'] = {**kwargs.get('context', {}), 'include_breakdowns': True}
    return ESGScoreSerializer(*args, **kwargs)


class DocumentSerializer(DynamicFieldsSerializer):
    doc_type_label = serializers.CharField(source='get_document_type_display', read_only=True)
    extraction = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        fields = [
            'id', 'supplier', 'file', 'document_type', 'doc_type_label',
            'file_format', 'uploaded_at', 'extraction',
        ]
        read_only_fields = ['id', 'uploaded_at']
    
    def get_extraction(self, obj):
        if not self.context.get('include_extraction', False):
            return None
        
        try:
            return ExtractedTextSerializer(
                obj.extraction,
                context={'include_keywords': True}
            ).data
        except ExtractedText.DoesNotExist:
            return None
    
    def validate_document_type(self, value):
        valid = [c[0] for c in Document.DOCUMENT_TYPES]
        if value not in valid:
            raise serializers.ValidationError(f"Invalid document_type. Allowed: {valid}")
        return value
    
    def validate_file_format(self, value):
        valid = [c[0] for c in Document.FORMATS]
        if value not in valid:
            raise serializers.ValidationError(f"Invalid file_format. Allowed: {valid}")
        return value
    
    def validate(self, attrs):
        """Validate file extension matches declared format."""
        file_obj = attrs.get('file')
        fmt = attrs.get('file_format', '')
        
        if file_obj:
            ext = file_obj.name.rsplit('.', 1)[-1].upper()
            if ext not in [f[0] for f in Document.FORMATS]:
                raise serializers.ValidationError(
                    {'file': f"Only PDF and DOCX files allowed. Got '.{ext}'."}
                )
            if ext != fmt.upper():
                raise serializers.ValidationError(
                    {'file_format': f"Declared format '{fmt}' does not match file extension '.{ext}'."}
                )
        return attrs


def DocumentListSerializer(*args, **kwargs):
    return DocumentSerializer(
        *args,
        fields=['id', 'file', 'document_type', 'doc_type_label', 'file_format', 'uploaded_at'],
        **kwargs
    )


def DocumentDetailSerializer(*args, **kwargs):
    kwargs['context'] = {**kwargs.get('context', {}), 'include_extraction': True}
    return DocumentSerializer(*args, **kwargs)


def DocumentCreateSerializer(*args, **kwargs):
    return DocumentSerializer(
        *args,
        fields=['id', 'supplier', 'file', 'document_type', 'file_format', 'uploaded_at'],
        **kwargs
    )


class SupplierSerializer(DynamicFieldsSerializer):
  
    cached_score = serializers.SerializerMethodField()
    cached_risk = serializers.SerializerMethodField()
    risk_label = serializers.SerializerMethodField()
    
    documents = serializers.SerializerMethodField()
    esg_score = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'country', 'category', 'created_at', 'updated_at',
            'cached_score', 'cached_risk', 'risk_label',
            'documents', 'esg_score',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_cached_score(self, obj):
        cache = getattr(obj, 'dashboard_cache', None)
        return cache.cached_score if cache else None
    
    def get_cached_risk(self, obj):
        cache = getattr(obj, 'dashboard_cache', None)
        return cache.cached_risk if cache else None
    
    def get_risk_label(self, obj):
        cache = getattr(obj, 'dashboard_cache', None)
        return cache.cached_risk if cache else 'N/A'
    
    def get_documents(self, obj):
        """Include documents only in detail context."""
        if not self.context.get('include_documents', False):
            return None
        return DocumentListSerializer(obj.documents.all(), many=True).data
    
    def get_esg_score(self, obj):
        if not self.context.get('include_esg', False):
            return None
        try:
            return ESGScoreDetailSerializer(obj.score).data
        except ESGScore.DoesNotExist:
            return None
    
    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Supplier name cannot be blank.")
        return value.strip()
    
    def validate_country(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Country cannot be blank.")
        return value.strip()


def SupplierListSerializer(*args, **kwargs):
    return SupplierSerializer(
        *args,
        fields=['id', 'name', 'country', 'category', 'cached_score', 'cached_risk', 
                'risk_label', 'created_at'],
        **kwargs
    )


def SupplierDetailSerializer(*args, **kwargs):
    kwargs['context'] = {
        **kwargs.get('context', {}),
        'include_documents': True,
        'include_esg': True,
    }
    return SupplierSerializer(*args, **kwargs)


def SupplierCreateSerializer(*args, **kwargs):
    return SupplierSerializer(
        *args,
        fields=['id', 'name', 'country', 'category'],
        **kwargs
    )


def SupplierUpdateSerializer(*args, **kwargs):
    return SupplierSerializer(
        *args,
        fields=['id', 'name', 'country', 'category'],
        **kwargs
    )