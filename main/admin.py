from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Category,
    Client,
    Product,
    Sale,
    SaleItem,
    TelegramLinkCode,
    TelegramOrder,
    TelegramOrderItem,
    TelegramProfile,
    User,
    WarehouseTransaction,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Qo'shimcha ma'lumotlar", {'fields': ('role', 'phone')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'unit', 'updated_at')
    list_filter = ('category',)
    search_fields = ('name', 'description')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'company', 'created_at')
    search_fields = ('name', 'phone', 'company', 'email')


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'seller', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'seller')
    search_fields = ('id', 'client__name', 'seller__username', 'seller__first_name', 'seller__last_name')
    inlines = [SaleItemInline]


@admin.register(WarehouseTransaction)
class WarehouseTransactionAdmin(admin.ModelAdmin):
    list_display = ('product', 'transaction_type', 'quantity', 'created_by', 'created_at')
    list_filter = ('transaction_type', 'created_by')
    search_fields = ('product__name', 'notes')


@admin.register(TelegramProfile)
class TelegramProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'chat_id', 'chat_username', 'is_active', 'linked_at', 'last_seen_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'chat_username', 'chat_id')


@admin.register(TelegramLinkCode)
class TelegramLinkCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'expires_at', 'is_used', 'created_at')
    list_filter = ('is_used',)
    search_fields = ('user__username', 'code')


class TelegramOrderItemInline(admin.TabularInline):
    model = TelegramOrderItem
    extra = 0


@admin.register(TelegramOrder)
class TelegramOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'phone', 'status', 'total_amount', 'created_at')
    list_filter = ('status',)
    search_fields = ('full_name', 'phone', 'profile__chat_username')
    inlines = [TelegramOrderItemInline]
