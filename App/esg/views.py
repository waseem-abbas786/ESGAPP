from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Supplier
from .serializers import SupplierListSerializer
from .models import Document
from .serializers import (
    DocumentListSerializer,
    DocumentDetailSerializer,
    DocumentCreateSerializer,
)

class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierListSerializer
    
    def get_serializer_class(self):
        from .serializers import (
            SupplierListSerializer,
            SupplierDetailSerializer,
            SupplierCreateSerializer,
            SupplierUpdateSerializer,
        )
        
        if self.action == "list":
            return SupplierListSerializer
        elif self.action == "retrieve":
            return SupplierDetailSerializer
        elif self.action == "create":
            return SupplierCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return SupplierUpdateSerializer
        return SupplierListSerializer

    def destroy(self, request, *args, **kwargs):
        supplier = self.get_object()
        supplier.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

from .models import Document

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    
    def get_serializer_class(self):
        from .serializers import (
            DocumentListSerializer,
            DocumentDetailSerializer,
            DocumentCreateSerializer,
        )
        if self.action == "list":
            return DocumentListSerializer
        elif self.action == "retrieve":
            return DocumentDetailSerializer
        elif self.action == "create":
            return DocumentCreateSerializer
        return DocumentListSerializer

    def destroy(self, request, *args, **kwargs):
        document = self.get_object()
        document.delete()
        return Response({"detail": "Document deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

