from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# ═══════════════════════════════════════════════════════════════
# DRF API Router
# ═══════════════════════════════════════════════════════════════
router = DefaultRouter()
router.register(r'suppliers', views.SupplierViewSet, basename='supplier')
router.register(r'documents', views.DocumentViewSet, basename='document')

# ═══════════════════════════════════════════════════════════════
# URL Patterns
# ═══════════════════════════════════════════════════════════════
urlpatterns = [
    # ─── API Endpoints ────────────────────────────────────────
    path('api/', include(router.urls)),
    
    # ─── Authentication ───────────────────────────────────────
    path('', views.CustomLoginView.as_view(), name='login'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('supplier/create/', views.admin_create_supplier, name='admin_create_supplier'), 
    path('supplier/<int:supplier_id>/', views.SupplierDetailView.as_view(), name='supplier_detail'),
    path('supplier/<int:supplier_id>/edit/', views.AdminEditSupplierView.as_view(), name='admin_edit_supplier'),
    
    path('supplier-dashboard/', views.SupplierDashboardView.as_view(), name='supplier_dashboard'),
    path('profile/edit/', views.SupplierEditProfileView.as_view(), name='supplier_edit_profile'),
    
    path('documents/', views.SupplierDocumentsView.as_view(), name='supplier_documents'),
    path('upload/', views.DocumentUploadView.as_view(), name='upload_document'),
    path('document/<int:document_id>/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('document/<int:document_id>/delete/', views.DocumentDeleteView.as_view(), name='delete_document'),
] 
