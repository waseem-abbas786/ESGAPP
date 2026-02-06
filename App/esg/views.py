
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from .models import Supplier, Document, ExtractedText, ESGScore, KeywordResult, ScoreBreakdown
from .serializers import (
    SupplierListSerializer,
    SupplierDetailSerializer,
    SupplierCreateSerializer,
    SupplierUpdateSerializer,
    DocumentListSerializer,
    DocumentDetailSerializer,
    DocumentCreateSerializer,
)
from .forms import LoginForm, DocumentUploadForm, SupplierEditForm


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierListSerializer
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "list":
            return SupplierListSerializer
        elif self.action == "retrieve":
            return SupplierDetailSerializer
        elif self.action == "create":
            return SupplierCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return SupplierUpdateSerializer
        return SupplierListSerializer
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return Supplier.objects.all()
        else:
            # Regular users can only see their own supplier
            try:
                return Supplier.objects.filter(user=self.request.user)
            except:
                return Supplier.objects.none()
    
    def destroy(self, request, *args, **kwargs):
        supplier = self.get_object()
        supplier_name = supplier.name
        supplier.delete()
        return Response(
            {"detail": f"Supplier '{supplier_name}' deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )


class DocumentViewSet(viewsets.ModelViewSet):

    queryset = Document.objects.all()
    parser_classes = (MultiPartParser, FormParser)
    
    def get_serializer_class(self):
        if self.action == "create":
            return DocumentCreateSerializer
        elif self.action == "retrieve":
            return DocumentDetailSerializer
        return DocumentListSerializer
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return Document.objects.all()
        else:
            try:
                supplier = self.request.user.supplier
                return Document.objects.filter(supplier=supplier)
            except:
                return Document.objects.none()
    
    def perform_create(self, serializer):
        """
        Set supplier when creating document.
        For non-staff users, automatically set their supplier.
        """
        if not self.request.user.is_staff:
            try:
                supplier = self.request.user.supplier
                serializer.save(supplier=supplier)
            except Supplier.DoesNotExist:
                from rest_framework.exceptions import ValidationError
                raise ValidationError("User is not linked to a supplier")
        else:
            serializer.save()
    
    def destroy(self, request, *args, **kwargs):
        document = self.get_object()
        if not request.user.is_staff:
            try:
                supplier = request.user.supplier
                if document.supplier != supplier:
                    return Response(
                        {"detail": "You can only delete your own documents."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except Supplier.DoesNotExist:
                return Response(
                    {"detail": "Access denied."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        document_name = document.file.name
        document.delete()
        return Response(
            {"detail": f"Document '{document_name}' deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )




def login_view(request):
    """
    Login view for both admin and supplier users.
    Redirects to appropriate dashboard based on user type.
    """
    # Redirect if already logged in
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('admin_dashboard')
        else:
            return redirect('supplier_dashboard')
    
    form = LoginForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # Success message
            messages.success(request, f'Welcome back, {user.username}!')
            
            # Redirect based on user type
            if user.is_staff:
                return redirect('admin_dashboard')
            else:
                return redirect('supplier_dashboard')
        else:
            form.add_error(None, "Invalid username or password")
    
    return render(request, 'esg/login.html', {'form': form})


@login_required
def logout_view(request):
    """Logout the current user."""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


# ============================================================================
# Admin Dashboard (Template-based)
# ============================================================================

@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to access the admin dashboard.')
        return redirect('supplier_dashboard')

    # Fetch suppliers and related objects
    suppliers = Supplier.objects.all().select_related('user').prefetch_related('documents')

    # Safely assign ESG fields from related score (if exists)
    for supplier in suppliers:
        supplier.esg_score = getattr(getattr(supplier, 'score', None), 'total_score', None)
        supplier.risk_level = getattr(getattr(supplier, 'score', None), 'risk_level', None)

    # Calculate statistics using updated fields
    high_risk_count = sum(1 for s in suppliers if s.risk_level == 'HIGH')
    medium_risk_count = sum(1 for s in suppliers if s.risk_level == 'MEDIUM')
    low_risk_count = sum(1 for s in suppliers if s.risk_level == 'LOW')

    context = {
        'suppliers': suppliers,
        'high_risk_count': high_risk_count,
        'medium_risk_count': medium_risk_count,
        'low_risk_count': low_risk_count,
    }

    return render(request, 'esg/admin_dashboard.html', context)



@login_required
def supplier_detail(request, supplier_id):
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('supplier_dashboard')
    
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    documents = supplier.documents.all().order_by('-uploaded_at')
    
    try:
        esg_score = supplier.score
    except ESGScore.DoesNotExist:
        esg_score = None
    
    context = {
        'supplier': supplier,
        'documents': documents,
        'esg_score': esg_score,
    }
    
    return render(request, 'esg/supplier_detail.html', context)


@login_required
def supplier_dashboard(request):
    """
    Supplier dashboard showing their own documents and ESG score.
    Only accessible to non-staff users linked to a supplier.
    """
    # Redirect staff to admin dashboard
    if request.user.is_staff:
        return redirect('admin_dashboard')
    
    # Get supplier for this user
    supplier = getattr(request.user, 'supplier', None)
    
    if supplier is None:
        messages.error(request, 'Your account is not linked to a supplier. Please contact admin.')
        logout(request)
        return redirect('login')
    
    # Get supplier's documents
    documents = supplier.documents.all().order_by('-uploaded_at')
    
    # Get ESG score
    try:
        esg_score = supplier.score
    except ESGScore.DoesNotExist:
        esg_score = None
    
    context = {
        'supplier': supplier,
        'documents': documents,
        'esg_score': esg_score,
    }
    
    return render(request, 'esg/supplier_dashboard.html', context)



@login_required
def supplier_documents(request):
    """
    View all documents for the supplier.
    """
    if request.user.is_staff:
        return redirect('admin_dashboard')
    
    try:
        supplier = request.user.supplier
    except Supplier.DoesNotExist:
        messages.error(request, 'Your account is not linked to a supplier.')
        return redirect('login')
    
    documents = supplier.documents.all().order_by('-uploaded_at')
    
    context = {
        'supplier': supplier,
        'documents': documents,
    }
    
    return render(request, 'esg/documents.html', context)


@login_required
def upload_document(request):
    """
    Upload a new document (supplier users only).
    """
    if request.user.is_staff:
        messages.error(request, 'Admins should use the admin panel to upload documents.')
        return redirect('admin_dashboard')
    
    try:
        supplier = request.user.supplier
    except Supplier.DoesNotExist:
        messages.error(request, 'Your account is not linked to a supplier.')
        return redirect('login')
    
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            document = form.save(commit=False)
            document.supplier = supplier
            document.save()
            
            messages.success(
                request,
                'Document uploaded successfully! ESG scoring will be completed automatically.'
            )
            return redirect('supplier_dashboard')
    else:
        form = DocumentUploadForm()
    
    context = {
        'form': form,
        'supplier': supplier,
    }
    
    return render(request, 'esg/upload_document.html', context)


@login_required
def document_detail(request, document_id):
    """
    View detailed information about a document.
    """
    document = get_object_or_404(Document, pk=document_id)
    
    if not request.user.is_staff:
        try:
            supplier = request.user.supplier
            if document.supplier != supplier:
                messages.error(request, 'You can only view your own documents.')
                return redirect('supplier_dashboard')
        except Supplier.DoesNotExist:
            messages.error(request, 'Access denied.')
            return redirect('login')
    
    extraction = None
    keywords = []
    keyword_summary = {'E': [], 'S': [], 'G': []}
    
    if hasattr(document, 'extraction'):
        extraction = document.extraction
        keywords = extraction.keywords.all().order_by('esg_category', 'keyword')
        
        for keyword in keywords:
            keyword_summary[keyword.esg_category].append(keyword)
    
    context = {
        'document': document,
        'extraction': extraction,
        'keywords': keywords,
        'keyword_summary': keyword_summary,
    }
    
    return render(request, 'esg/document_detail.html', context)


@login_required
def delete_document(request, document_id):
    """
    Delete a document (suppliers can only delete their own).
    """
    if request.method != 'POST':
        return redirect('supplier_dashboard')
    
    document = get_object_or_404(Document, pk=document_id)
    
    # Check permissions
    if not request.user.is_staff:
        try:
            supplier = request.user.supplier
            if document.supplier != supplier:
                messages.error(request, 'You can only delete your own documents.')
                return redirect('supplier_dashboard')
        except Supplier.DoesNotExist:
            messages.error(request, 'Access denied.')
            return redirect('login')
    
    document_name = document.file.name
    document.delete()
    
    messages.success(request, f'Document "{document_name}" deleted successfully.')
    
    if request.user.is_staff:
        return redirect('admin_dashboard')
    else:
        return redirect('supplier_dashboard')
    

@login_required
def supplier_edit_profile(request):
    """
    Allow suppliers to edit their own profile.
    Staff users are redirected to admin.
    """
    if request.user.is_staff:
        messages.info(request, 'Admins should use the admin panel to edit suppliers.')
        return redirect('admin_dashboard')
    
    try:
        supplier = request.user.supplier
    except Supplier.DoesNotExist:
        messages.error(request, 'Your account is not linked to a supplier.')
        return redirect('login')
    
    if request.method == 'POST':
        form = SupplierEditForm(request.POST, instance=supplier)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('supplier_dashboard')
    else:
        form = SupplierEditForm(instance=supplier)
    
    context = {
        'form': form,
        'supplier': supplier,
    }
    
    return render(request, 'esg/supplier_edit_profile.html', context)


@login_required
def admin_edit_supplier(request, supplier_id):
    """
    Allow admin to edit any supplier.
    Non-staff users are redirected.
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('supplier_dashboard')
    
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    
    if request.method == 'POST':
        form = SupplierEditForm(request.POST, instance=supplier)
        
        if form.is_valid():
            form.save()
            messages.success(request, f'Supplier "{supplier.name}" has been updated successfully!')
            return redirect('admin_dashboard')
    else:
        form = SupplierEditForm(instance=supplier)
    
    context = {
        'form': form,
        'supplier': supplier,
        'is_admin_edit': True,  
    }
    
    return render(request, 'esg/admin_edit_supplier.html', context)