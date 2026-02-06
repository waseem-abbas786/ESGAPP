# forms.py - Complete version with all forms

from django import forms
from .models import Supplier, Document


class LoginForm(forms.Form):
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