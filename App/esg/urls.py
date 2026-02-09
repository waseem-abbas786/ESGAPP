
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'suppliers', views.SupplierViewSet, basename='supplier')
router.register(r'documents', views.DocumentViewSet, basename='document')

urlpatterns = [
    path('', views.login_view, name='login'), 
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('supplier/<int:supplier_id>/', views.supplier_detail, name='supplier_detail'),
    path('supplier/<int:supplier_id>/edit/', views.admin_edit_supplier, name='admin_edit_supplier'),
    path('profile/edit/', views.supplier_edit_profile, name='supplier_edit_profile'), 
    path('supplier-dashboard/', views.supplier_dashboard, name='supplier_dashboard'),
    path('documents/', views.supplier_documents, name='supplier_documents'),
    path('upload/', views.upload_document, name='upload_document'),
    path('document/<int:document_id>/', views.document_detail, name='document_detail'),
    path('document/<int:document_id>/delete/', views.delete_document, name='delete_document'),
    path('api/', include(router.urls)),
]
