from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Supplier
from .serializers import SupplierListSerializer

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

