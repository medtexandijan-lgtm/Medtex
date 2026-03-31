from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from main import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', views.login_view, name='login'),
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('kassa/', views.kassa, name='kassa'),
    path('kassa/sell/<int:product_id>/', views.kassa_sell, name='kassa_sell'),
    path('users/', views.users_list, name='users'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('categories/', views.categories_list, name='categories'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('products/', views.products_list, name='products'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('clients/', views.clients_list, name='clients'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    path('sales/', views.sales_list, name='sales'),
    path('sales/create/', views.sale_create, name='sale_create'),
    path('sales/<int:pk>/', views.sale_detail, name='sale_detail'),
    path('sales/<int:pk>/status/', views.sale_update_status, name='sale_update_status'),
    path('warehouse/', views.warehouse, name='warehouse'),
    path('warehouse/transaction/', views.warehouse_transaction, name='warehouse_transaction'),
    path('transactions/', views.transactions_history, name='transactions'),
    path('reports/', views.reports, name='reports'),
    path('telegram-orders/', views.telegram_orders_list, name='telegram_orders'),
    path('telegram-orders/<int:pk>/', views.telegram_order_detail, name='telegram_order_detail'),
    path('telegram-orders/<int:pk>/status/', views.telegram_order_update_status, name='telegram_order_update_status'),
    path('mini-app/', views.mini_app, name='mini_app'),
    path('mini-app/auth/', views.mini_app_auth, name='mini_app_auth'),
    path('mini-app/orders/', views.mini_app_create_order, name='mini_app_create_order'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),
    path('api/product-price/', views.get_product_price, name='product_price'),
    path('api/product-select/', views.product_select, name='product_select'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
