from django import forms
from django.contrib.auth.forms import UserCreationForm as AuthUserCreationForm, UserChangeForm as AuthUserChangeForm
from .models import User, Category, Product, Client, Sale, SaleItem, WarehouseTransaction


class UserCreationForm(AuthUserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'phone')


class UserChangeForm(AuthUserChangeForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'phone')


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'description')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kategoriya nomi'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Tavsif'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ('name', 'category', 'description', 'price', 'stock', 'unit', 'image')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mahsulot nomi'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Tavsif'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Narxi'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Soni'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Oʻlchov birligi'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ('name', 'phone', 'email', 'address', 'company')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mijoz nomi'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Telefon'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Manzil'}),
            'company': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kompaniya'}),
        }


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ('client', 'status', 'notes')
        widgets = {
            'client': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Izoh'}),
        }


class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ('product', 'quantity')
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control product-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }


class WarehouseTransactionForm(forms.ModelForm):
    class Meta:
        model = WarehouseTransaction
        fields = ('product', 'transaction_type', 'quantity', 'notes')
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Izoh'}),
        }


class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Foydalanuvchi nomi'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Parol'})
    )