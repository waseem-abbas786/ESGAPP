# forms.py - Complete version with all forms

from django import forms
from .models import Supplier, Document
from django.contrib.auth.forms import AuthenticationForm

class LoginForm(AuthenticationForm):
    """
    Login form for both admin and supplier users.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Enter your username',
            'autofocus': True,
        }),
        label='Username'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Enter your password'
        }),
        label='Password'
    )


class DocumentUploadForm(forms.ModelForm):
    """
    Form for suppliers to upload documents.
    """
    class Meta:
        model = Document
        fields = ['document_type', 'file', 'file_format']
        widgets = {
            'document_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
            }),
            'file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.docx'
            }),
            'file_format': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
            }),
        }
        labels = {
            'document_type': 'Document Type',
            'file': 'Select File',
            'file_format': 'File Format',
        }
        help_texts = {
            'file': 'Upload PDF or DOCX files only (max 10MB)',
            'document_type': 'Select the type of document you are uploading',
            'file_format': 'Select the format of your document',
        }
    
    def clean_file(self):
        """Validate file size and extension."""
        file = self.cleaned_data.get('file')
        
        if file:
            # Check file size (10MB limit)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('File size cannot exceed 10MB.')
            
            # Check file extension
            ext = file.name.rsplit('.', 1)[-1].upper()
            if ext not in ['PDF', 'DOCX']:
                raise forms.ValidationError('Only PDF and DOCX files are allowed.')
        
        return file
    
    def clean(self):
        """Validate that file format matches file extension."""
        cleaned_data = super().clean()
        uploaded_file = cleaned_data.get('file')
        declared_format = cleaned_data.get('file_format')
        
        if uploaded_file and declared_format:
            ext = uploaded_file.name.rsplit('.', 1)[-1].upper()
            
            if ext != declared_format:
                raise forms.ValidationError(
                    f'File format mismatch: File is .{ext} but you selected {declared_format}'
                )
        
        return cleaned_data


class SupplierForm(forms.ModelForm):
    """
    Form for creating/editing suppliers (admin use).
    """
    class Meta:
        model = Supplier
        fields = ['supplier_code', 'name', 'country', 'category']
        widgets = {
            'supplier_code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'e.g., SUP001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Supplier Name'
            }),
            'country': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'Country'
            }),
            'category': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg',
                'placeholder': 'e.g., Manufacturing'
            }),
        }
    
    def clean_supplier_code(self):
        """Ensure supplier code is unique."""
        supplier_code = self.cleaned_data.get('supplier_code')
        
        # Check if editing existing supplier
        if self.instance.pk:
            if Supplier.objects.exclude(pk=self.instance.pk).filter(supplier_code=supplier_code).exists():
                raise forms.ValidationError('This supplier code already exists.')
        else:
            if Supplier.objects.filter(supplier_code=supplier_code).exists():
                raise forms.ValidationError('This supplier code already exists.')
        
        return supplier_code
    



class SupplierEditForm(forms.ModelForm):
    """
    Form for suppliers to edit their profile.
    Excludes supplier_code, esg_score, risk_level (auto-calculated fields).
    """
    
    class Meta:
        model = Supplier
        fields = ['name', 'country', 'category']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Company Name'
            }),
            'country': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Country'
            }),
            'category': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'e.g., Manufacturing, Technology, Services'
            }),
        }
        labels = {
            'name': 'Company Name',
            'country': 'Country',
            'category': 'Business Category',
        }
        help_texts = {
            'name': 'Your official company name',
            'country': 'Country where your company is registered',
            'category': 'Primary business category or industry',
        }
    
    def clean_name(self):
        """Ensure name is not empty."""
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Company name cannot be blank.')
        return name
    
    def clean_country(self):
        """Ensure country is not empty."""
        country = self.cleaned_data.get('country', '').strip()
        if not country:
            raise forms.ValidationError('Country cannot be blank.')
        return country
    
    def clean_category(self):
        """Ensure category is not empty."""
        category = self.cleaned_data.get('category', '').strip()
        if not category:
            raise forms.ValidationError('Category cannot be blank.')
        return category
    


class SupplierCreateForm(forms.ModelForm):
    """
    Form for admin to create a new supplier.
    """
    
    class Meta:
        model = Supplier
        fields = ['supplier_code', 'name', 'country', 'category']
        widgets = {
            'supplier_code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'e.g., SUP001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Company Name'
            }),
            'country': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Country'
            }),
            'category': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'e.g., Manufacturing, Technology'
            }),
        }
        labels = {
            'supplier_code': 'Supplier Code',
            'name': 'Company Name',
            'country': 'Country',
            'category': 'Business Category',
        }
        help_texts = {
            'supplier_code': 'Unique identifier (will be used for username)',
            'name': 'Official company name',
            'country': 'Country of registration',
            'category': 'Primary business category',
        }
    
    def clean_supplier_code(self):
        """
        Validate supplier code is unique and format it properly.
        """
        supplier_code = self.cleaned_data.get('supplier_code', '').strip()
        
        if not supplier_code:
            raise forms.ValidationError('Supplier code is required.')
        
        # Check if already exists
        if Supplier.objects.filter(supplier_code=supplier_code).exists():
            raise forms.ValidationError(
                f'Supplier code "{supplier_code}" already exists. Please use a different code.'
            )
        
        # Check if username would conflict
        from django.contrib.auth.models import User
        username = supplier_code.lower().replace(' ', '_')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(
                f'A user with username "{username}" already exists. Please use a different supplier code.'
            )
        
        return supplier_code
    
    def clean_name(self):
        """Ensure name is not empty."""
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Company name is required.')
        return name
    
    def clean_country(self):
        """Ensure country is not empty."""
        country = self.cleaned_data.get('country', '').strip()
        if not country:
            raise forms.ValidationError('Country is required.')
        return country
    
    def clean_category(self):
        """Ensure category is not empty."""
        category = self.cleaned_data.get('category', '').strip()
        if not category:
            raise forms.ValidationError('Category is required.')
        return category