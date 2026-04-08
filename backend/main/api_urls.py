from django.urls import path

from . import api_views


urlpatterns = [
    path('', api_views.ApiRootView.as_view(), name='api_root'),
    path('auth/login/', api_views.ApiLoginView.as_view(), name='api_login'),
    path('auth/logout/', api_views.ApiLogoutView.as_view(), name='api_logout'),
    path('auth/me/', api_views.ApiMeView.as_view(), name='api_me'),
    path('categories/', api_views.CategoryListApiView.as_view(), name='api_categories'),
    path('products/', api_views.ProductListApiView.as_view(), name='api_products'),
    path('clients/', api_views.ClientListApiView.as_view(), name='api_clients'),
    path('sales/', api_views.SaleListCreateApiView.as_view(), name='api_sales'),
    path('sales/<int:pk>/', api_views.SaleDetailApiView.as_view(), name='api_sale_detail'),
    path('shifts/', api_views.ShiftListApiView.as_view(), name='api_shifts'),
    path('shifts/current/', api_views.CurrentShiftApiView.as_view(), name='api_current_shift'),
    path('shifts/start/', api_views.ShiftStartApiView.as_view(), name='api_shift_start'),
    path('shifts/end/', api_views.ShiftEndApiView.as_view(), name='api_shift_end'),
    path('shifts/<int:pk>/report/', api_views.ShiftReportApiView.as_view(), name='api_shift_report'),
    path('courier/auth/login/', api_views.CourierLoginApiView.as_view(), name='api_courier_login'),
    path('courier/auth/me/', api_views.CourierMeApiView.as_view(), name='api_courier_me'),
    path('courier/dashboard/', api_views.CourierDashboardApiView.as_view(), name='api_courier_dashboard'),
    path('courier/orders/', api_views.CourierOrderListApiView.as_view(), name='api_courier_orders'),
    path('courier/orders/<int:pk>/', api_views.CourierOrderDetailApiView.as_view(), name='api_courier_order_detail'),
    path('courier/orders/<int:pk>/accept/', api_views.CourierOrderAcceptApiView.as_view(), name='api_courier_order_accept'),
    path('courier/orders/<int:pk>/complete/', api_views.CourierOrderCompleteApiView.as_view(), name='api_courier_order_complete'),
]
