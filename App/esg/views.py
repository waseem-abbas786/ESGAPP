from django.shortcuts import redirect,render
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError

from .models import Supplier, Document
from .serializers import (
    SupplierListSerializer, SupplierDetailSerializer,
    SupplierCreateSerializer, SupplierUpdateSerializer,
    DocumentListSerializer, DocumentDetailSerializer,
    DocumentCreateSerializer,
)
from .forms import LoginForm, DocumentUploadForm, SupplierEditForm, SupplierCreateForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.contrib.auth.hashers import make_password
import secrets
import string


class ContextualSerializerMixin:
    """Returns different serializers based on action."""
    serializer_map = {}
    
    def get_serializer_class(self):
        return self.serializer_map.get(self.action, self.serializer_class)


class SupplierOwnershipMixin:
    """Filters queryset: staff sees all, users see only their own."""
    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        try:
            return self.queryset.filter(user=self.request.user)
        except:
            return self.queryset.none()


class DocumentOwnershipMixin:
    """Filters queryset: staff sees all, users see only their supplier's docs."""
    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        try:
            return self.queryset.filter(supplier=self.request.user.supplier)
        except:
            return self.queryset.none()
    
    def _check_document_ownership(self, document):
        """Raises 403 if non-staff user doesn't own this document."""
        if self.request.user.is_staff:
            return
        try:
            if document.supplier != self.request.user.supplier:
                raise ValidationError("You can only access your own documents.")
        except Supplier.DoesNotExist:
            raise ValidationError("Access denied.")



class SupplierViewSet(ContextualSerializerMixin, SupplierOwnershipMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierListSerializer
    serializer_map = {
        'list': SupplierListSerializer,
        'retrieve': SupplierDetailSerializer,
        'create': SupplierCreateSerializer,
        'update': SupplierUpdateSerializer,
        'partial_update': SupplierUpdateSerializer,
    }
    
    def destroy(self, request, *args, **kwargs):
        supplier = self.get_object()
        name = supplier.name
        supplier.delete()
        return Response(
            {'detail': f"Supplier '{name}' deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )


class DocumentViewSet(ContextualSerializerMixin, DocumentOwnershipMixin, viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentListSerializer
    parser_classes = (MultiPartParser, FormParser)
    serializer_map = {
        'list': DocumentListSerializer,
        'retrieve': DocumentDetailSerializer,
        'create': DocumentCreateSerializer,
    }
    
    def perform_create(self, serializer):
        """Auto-assign supplier for non-staff users."""
        if not self.request.user.is_staff:
            try:
                serializer.save(supplier=self.request.user.supplier)
            except Supplier.DoesNotExist:
                raise ValidationError("User is not linked to a supplier")
        else:
            serializer.save()
    
    def destroy(self, request, *args, **kwargs):
        document = self.get_object()
        self._check_document_ownership(document)
        
        name = document.file.name
        document.delete()
        return Response(
            {'detail': f"Document '{name}' deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )



class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only staff users can access."""
    def test_func(self):
        return self.request.user.is_staff
    
    def handle_no_permission(self):
        messages.error(self.request, 'You do not have permission to access the admin dashboard.')
        return redirect('supplier_dashboard')


class SupplierUserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only non-staff users with a linked supplier can access."""
    def test_func(self):
        if self.request.user.is_staff:
            return False
        return hasattr(self.request.user, 'supplier')
    
    def handle_no_permission(self):
        if self.request.user.is_staff:
            return redirect('admin_dashboard')
        
        messages.error(self.request, 'Your account is not linked to a supplier. Please contact admin.')
        logout(self.request)
        return redirect('login')


class SupplierContextMixin:
    """Adds supplier object to context."""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supplier'] = getattr(self.request.user, 'supplier', None)
        return context


class ESGScoreContextMixin:
    """Adds ESG score to context for the current supplier."""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier = context.get('supplier') or getattr(self.request.user, 'supplier', None)
        context['esg_score'] = getattr(supplier, 'score', None) if supplier else None
        return context


class CustomLoginView(LoginView):
    template_name = 'esg/login.html'
    form_class = LoginForm
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('admin_dashboard' if self.request.user.is_staff else 'supplier_dashboard')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Welcome back, {self.request.user.username}!')
        return response


class CustomLogoutView(LoginRequiredMixin, LogoutView):
    next_page = 'login'
    
    def dispatch(self, request, *args, **kwargs):
        messages.success(request, 'You have been logged out successfully.')
        return super().dispatch(request, *args, **kwargs)


class AdminDashboardView(StaffRequiredMixin, ListView):
    model = Supplier
    template_name = 'esg/admin_dashboard.html'
    context_object_name = 'suppliers'
    
    def get_queryset(self):
        return Supplier.objects.select_related('user').prefetch_related('documents')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        suppliers = context['suppliers']
        for s in suppliers:
            s.esg_score = getattr(getattr(s, 'score', None), 'total_score', None)
            s.risk_level = getattr(getattr(s, 'score', None), 'risk_level', None)
        
        risk_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for s in suppliers:
            risk_counts[s.risk_level or 'HIGH'] += 1
        
        context['high_risk_count'] = risk_counts['HIGH']
        context['medium_risk_count'] = risk_counts['MEDIUM']
        context['low_risk_count'] = risk_counts['LOW']
        
        return context


class SupplierDetailView(StaffRequiredMixin, DetailView):
    model = Supplier
    template_name = 'esg/supplier_detail.html'
    context_object_name = 'supplier'
    pk_url_kwarg = 'supplier_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.order_by('-uploaded_at')
        context['esg_score'] = getattr(self.object, 'score', None)
        return context


class AdminEditSupplierView(StaffRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierEditForm
    template_name = 'esg/admin_supplier_edit.html'
    pk_url_kwarg = 'supplier_id'
    success_url = reverse_lazy('admin_dashboard')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supplier'] = self.object
        context['is_admin_edit'] = True
        return context
    
    def form_valid(self, form):
        messages.success(self.request, f'Supplier "{self.object.name}" has been updated successfully!')
        return super().form_valid(form)


class SupplierDashboardView(SupplierUserRequiredMixin, SupplierContextMixin, ESGScoreContextMixin, ListView):
    model = Document
    template_name = 'esg/supplier_dashboard.html'
    context_object_name = 'documents'
    
    def get_queryset(self):
        return self.request.user.supplier.documents.order_by('-uploaded_at')


class SupplierEditProfileView(SupplierUserRequiredMixin, SupplierContextMixin, UpdateView):
    model = Supplier
    form_class = SupplierEditForm
    template_name = 'esg/supplier_edit_profile.html'
    success_url = reverse_lazy('supplier_dashboard')
    
    def get_object(self, queryset=None):
        return self.request.user.supplier
    
    def form_valid(self, form):
        messages.success(self.request, 'Your profile has been updated successfully!')
        return super().form_valid(form)


class SupplierDocumentsView(SupplierUserRequiredMixin, SupplierContextMixin, ListView):
    model = Document
    template_name = 'esg/documents.html'
    context_object_name = 'documents'
    
    def get_queryset(self):
        return self.request.user.supplier.documents.order_by('-uploaded_at')


class DocumentUploadView(SupplierUserRequiredMixin, SupplierContextMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = 'esg/upload_document.html'
    success_url = reverse_lazy('supplier_dashboard')
    
    def form_valid(self, form):
        form.instance.supplier = self.request.user.supplier
        messages.success(
            self.request,
            'Document uploaded successfully! ESG scoring will be completed automatically.'
        )
        return super().form_valid(form)


class DocumentDetailView(LoginRequiredMixin, DetailView):
    model = Document
    template_name = 'esg/document_detail.html'
    context_object_name = 'document'
    pk_url_kwarg = 'document_id'
    
    def dispatch(self, request, *args, **kwargs):
        """Check ownership for non-staff users."""
        document = self.get_object()
        
        if not request.user.is_staff:
            try:
                if document.supplier != request.user.supplier:
                    messages.error(request, 'You can only view your own documents.')
                    return redirect('supplier_dashboard')
            except:
                messages.error(request, 'Access denied.')
                return redirect('login')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        extraction = getattr(self.object, 'extraction', None)
        keywords = extraction.keywords.order_by('esg_category', 'keyword') if extraction else []
        
        keyword_summary = {'E': [], 'S': [], 'G': []}
        for kw in keywords:
            keyword_summary[kw.esg_category].append(kw)
        
        context['extraction'] = extraction
        context['keywords'] = keywords
        context['keyword_summary'] = keyword_summary
        
        return context


class DocumentDeleteView(LoginRequiredMixin, DeleteView):
    model = Document
    pk_url_kwarg = 'document_id'
    
    def get_success_url(self):
        return reverse_lazy('admin_dashboard' if self.request.user.is_staff else 'supplier_dashboard')
    
    def dispatch(self, request, *args, **kwargs):
        """Only allow POST and check ownership."""
        if request.method != 'POST':
            return redirect('supplier_dashboard')
        
        document = self.get_object()
        
        if not request.user.is_staff:
            try:
                if document.supplier != request.user.supplier:
                    messages.error(request, 'You can only delete your own documents.')
                    return redirect('supplier_dashboard')
            except:
                messages.error(request, 'Access denied.')
                return redirect('login')
        
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        document = self.get_object()
        name = document.file.name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Document "{name}" deleted successfully.')
        return response
    
# Add these views to your views.py




@login_required
def admin_create_supplier(request):
    """
    Allow admin to create a new supplier with automatic user account creation.
    Shows username and password after creation.
    """
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Only admins can create suppliers.')
        return redirect('supplier_dashboard')
    
    if request.method == 'POST':
        form = SupplierCreateForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create supplier
                    supplier = form.save(commit=False)
                    supplier.esg_score = 0
                    supplier.risk_level = 'HIGH'
                    supplier.save()
                    
                    # Check if user account should be created
                    create_user = request.POST.get('create_user_account') == 'on'
                    credentials = None
                    
                    if create_user:
                        # Generate username from supplier code
                        username = supplier.supplier_code.lower().replace(' ', '_')
                        
                        # Check if username already exists
                        if User.objects.filter(username=username).exists():
                            raise ValueError(f"Username '{username}' already exists")
                        
                        # Generate random secure password
                        password = generate_secure_password()
                        
                        # Get email or generate default
                        email = request.POST.get('email', '').strip()
                        if not email:
                            email = f"{username}@supplier.local"
                        
                        # Create user
                        user = User.objects.create(
                            username=username,
                            email=email,
                            password=make_password(password),
                            is_staff=False,
                            is_active=True
                        )
                        
                        # Link user to supplier
                        supplier.user = user
                        supplier.save()
                        
                        # Store credentials to display
                        credentials = {
                            'username': username,
                            'password': password,  # Plain text for display only
                            'email': email
                        }
                        
                        messages.success(
                            request,
                            f'Supplier "{supplier.name}" created successfully with user account!'
                        )
                    else:
                        messages.success(
                            request,
                            f'Supplier "{supplier.name}" created successfully!'
                        )
                    
                    # Redirect to success page with credentials
                    return render(request, 'esg/supplier_created_success.html', {
                        'supplier': supplier,
                        'credentials': credentials
                    })
                    
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Error creating supplier: {str(e)}')
    else:
        form = SupplierCreateForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'esg/admin_create_supplier.html', context)


def generate_secure_password(length=12):
    """
    Generate a secure random password.
    
    Args:
        length: Password length (default: 12)
    
    Returns:
        Secure random password with uppercase, lowercase, digits, and special chars
    """
    # Define character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special = '!@#$%^&*'
    
    # Ensure at least one character from each set
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(special)
    ]
    
    # Fill the rest with random characters from all sets
    all_chars = lowercase + uppercase + digits + special
    password += [secrets.choice(all_chars) for _ in range(length - 4)]
    
    # Shuffle to avoid predictable pattern
    secrets.SystemRandom().shuffle(password)
    
    return ''.join(password)