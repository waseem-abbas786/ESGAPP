from rest_framework import serializers
from .models import (
    Supplier,
    Document,
    ExtractedText,
    KeywordResult,
    ESGScore,
    ScoreBreakdown,
)

class ScoreBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreBreakdown
        fields = [
            "id",
            "factor_name",
            "max_points",
            "earned_points",
            "achieved",
        ]
        read_only_fields = fields


class KeywordResultSerializer(serializers.ModelSerializer):
    esg_category_label = serializers.CharField(
        source="get_esg_category_display", read_only=True
    )

    class Meta:
        model = KeywordResult
        fields = [
            "id",
            "esg_category",
            "esg_category_label",
            "keyword",
            "found",
            "points_awarded",
        ]
        read_only_fields = fields


class KeywordResultMapSerializer(serializers.Serializer):
    _KEY_MAP = {
        "environmental policy": "environmental_policy",
        "carbon emissions": "mentions_emissions",
        "iso 14001": "has_iso_14001",
        "renewable energy": "renewable_energy",
        "labour rights": "labour_rights",
        "human rights": "human_rights",
        "health and safety": "health_safety",
        "diversity and inclusion": "diversity_inclusion",
        "anti-corruption": "anti_corruption",
        "ethics policy": "ethics_policy",
        "whistleblowing": "whistleblowing",
        "governance structure": "governance_structure",
        "supply chain responsibility": "supply_chain_responsibility",
    }

    def to_representation(self, keyword_qs):
        result = {}
        for kr in keyword_qs:
            out_key = self._KEY_MAP.get(kr.keyword.lower())
            if out_key:
                result[out_key] = kr.found
        return result


class ExtractedTextSerializer(serializers.ModelSerializer):
    keyword_results = KeywordResultSerializer(
        source="keywords", many=True, read_only=True
    )

    class Meta:
        model = ExtractedText
        fields = [
            "id",
            "raw_text",
            "extractor_lib",
            "extracted_at",
            "keyword_results",
        ]
        read_only_fields = fields


class ExtractedTextLightSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractedText
        fields = ["id", "extractor_lib", "extracted_at"]
        read_only_fields = fields


class DocumentListSerializer(serializers.ModelSerializer):
    doc_type_label = serializers.CharField(
        source="get_document_type_display", read_only=True
    )

    class Meta:
        model = Document
        fields = [
            "id",
            "file",
            "document_type",
            "doc_type_label",
            "file_format",
            "uploaded_at",
        ]
        read_only_fields = fields


class DocumentDetailSerializer(serializers.ModelSerializer):
    extraction = ExtractedTextSerializer(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "file",
            "document_type",
            "file_format",
            "uploaded_at",
            "extraction",
        ]
        read_only_fields = fields


class DocumentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "supplier",
            "file",
            "document_type",
            "file_format",
            "uploaded_at",
        ]
        read_only_fields = ["id", "uploaded_at"]

    def validate_document_type(self, value):
        valid = [choice[0] for choice in Document.DOCUMENT_TYPES]
        if value not in valid:
            raise serializers.ValidationError(f"Invalid document_type. Allowed: {valid}")
        return value

    def validate_file_format(self, value):
        valid = [choice[0] for choice in Document.FORMATS]
        if value not in valid:
            raise serializers.ValidationError(f"Invalid file_format. Allowed: {valid}")
        return value

    def validate(self, attrs):
        uploaded_file = attrs.get("file")
        declared_fmt = attrs.get("file_format", "")

        if uploaded_file:
            ext = uploaded_file.name.rsplit(".", 1)[-1].upper()
            if ext not in [f[0] for f in Document.FORMATS]:
                raise serializers.ValidationError(
                    {"file": f"Only PDF and DOCX files are allowed. Got '.{ext}'."}
                )
            if ext != declared_fmt.upper():
                raise serializers.ValidationError(
                    {"file_format": f"Declared format '{declared_fmt}' does not match file extension '.{ext}'."}
                )
        return attrs

    def create(self, validated_data):
        # Single DB save; file is part of model fields so it will be saved in same create()
        return Document.objects.create(**validated_data)


class ESGScoreListSerializer(serializers.ModelSerializer):
    risk_level_label = serializers.CharField(source="get_risk_level_display", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = ESGScore
        fields = [
            "id",
            "supplier_name",
            "total_score",
            "risk_level",
            "risk_level_label",
            "env_points",
            "social_points",
            "governance_points",
            "calculated_at",
        ]
        read_only_fields = fields


class ESGScoreDetailSerializer(serializers.ModelSerializer):
    risk_level_label = serializers.CharField(source="get_risk_level_display", read_only=True)
    breakdowns = ScoreBreakdownSerializer(source="breakdown", many=True, read_only=True)

    class Meta:
        model = ESGScore
        fields = [
            "id",
            "supplier",
            "total_score",
            "risk_level",
            "risk_level_label",
            "env_points",
            "social_points",
            "governance_points",
            "calculated_at",
            "breakdowns",
        ]
        read_only_fields = fields


class ESGScoreCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ESGScore
        fields = [
            "id",
            "supplier",
            "total_score",
            "risk_level",
            "env_points",
            "social_points",
            "governance_points",
            "calculated_at",
        ]
        read_only_fields = ["id", "risk_level", "calculated_at"]

    def validate_total_score(self, value):
        if not (0 <= value <= 100):
            raise serializers.ValidationError("total_score must be between 0 and 100.")
        return value


class SupplierListSerializer(serializers.ModelSerializer):
    cached_score = serializers.SerializerMethodField()
    cached_risk = serializers.SerializerMethodField()
    risk_label = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "country",
            "category",
            "cached_score",
            "cached_risk",
            "risk_label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @staticmethod
    def get_cached_score(obj):
        cache = getattr(obj, "dashboard_cache", None)
        return cache.cached_score if cache else None

    @staticmethod
    def get_cached_risk(obj):
        cache = getattr(obj, "dashboard_cache", None)
        return cache.cached_risk if cache else None

    @staticmethod
    def get_risk_label(obj):
        cache = getattr(obj, "dashboard_cache", None)
        return cache.cached_risk if cache else "N/A"


class SupplierDetailSerializer(serializers.ModelSerializer):
    documents = DocumentListSerializer(many=True, read_only=True)
    esg_score = ESGScoreDetailSerializer(source="score", read_only=True)
    
    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "country",
            "category",
            "created_at",
            "updated_at",
            "documents",
            "esg_score",
            "audit_logs",
        ]
        read_only_fields = fields


class SupplierCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "supplier_code", "name", "country", "category", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Supplier name cannot be blank.")
        return value.strip()

    def validate_country(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Country cannot be blank.")
        return value.strip()


class SupplierUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "country", "category", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Supplier name cannot be blank.")
        return value.strip()
