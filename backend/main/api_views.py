from django.contrib.auth import authenticate, login, logout
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Client, Product, Sale, SaleItem, SellerShift, TelegramOrder, User, WarehouseTransaction
from .serializers import (
    CategorySerializer,
    ClientSerializer,
    CourierOrderSerializer,
    CourierStatsSerializer,
    ProductSerializer,
    SaleCreateSerializer,
    SaleSerializer,
    SellerShiftReportSerializer,
    SellerShiftSerializer,
    UserSummarySerializer,
)
from .views import build_shift_report_context, get_active_shift, notify_order_profile


COURIER_TOKEN_SALT = 'courier-mobile-auth'


class IsDirector(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'director'


class IsDirectorOrSeller(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {'director', 'seller'}


class IsCourier(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in {'supplier', 'courier'}


def issue_courier_token(user):
    payload = {
        'user_id': user.id,
        'role': user.role,
    }
    return signing.dumps(payload, salt=COURIER_TOKEN_SALT)


def get_courier_user_from_request(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(' ', 1)[1].strip()
    if not token:
        return None

    try:
        payload = signing.loads(token, salt=COURIER_TOKEN_SALT, max_age=604800)
    except signing.BadSignature:
        return None

    return User.objects.filter(
        id=payload.get('user_id'),
        role__in={'supplier', 'courier'},
        is_active=True,
    ).first()


def get_courier_orders_queryset(user):
    return TelegramOrder.objects.filter(
        Q(courier=user) | Q(courier__isnull=True, status__in={'new', 'confirmed'})
    ).select_related('profile__user', 'sale', 'courier').prefetch_related('items__product').order_by('-created_at')


class CourierApiBaseView(APIView):
    permission_classes = [permissions.AllowAny]

    def dispatch(self, request, *args, **kwargs):
        request.courier_user = get_courier_user_from_request(request)
        return super().dispatch(request, *args, **kwargs)

    def require_courier(self, request):
        user = getattr(request, 'courier_user', None)
        if not user:
            return None, Response({'detail': 'Kuryer autentifikatsiyasi topilmadi'}, status=status.HTTP_401_UNAUTHORIZED)
        return user, None


class ApiRootView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(
            {
                'auth': {
                    'login': '/api/v1/auth/login/',
                    'logout': '/api/v1/auth/logout/',
                    'me': '/api/v1/auth/me/',
                },
                'resources': {
                    'categories': '/api/v1/categories/',
                    'products': '/api/v1/products/',
                    'clients': '/api/v1/clients/',
                    'sales': '/api/v1/sales/',
                    'shifts': '/api/v1/shifts/',
                    'current_shift': '/api/v1/shifts/current/',
                },
            }
        )


class ApiLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({'detail': "Foydalanuvchi nomi yoki parol noto'g'ri"}, status=status.HTTP_400_BAD_REQUEST)

        login(request, user)
        return Response({'user': UserSummarySerializer(user).data})


class ApiLogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApiMeView(APIView):
    def get(self, request):
        payload = UserSummarySerializer(request.user).data
        active_shift = get_active_shift(request.user)
        payload['active_shift'] = SellerShiftSerializer(active_shift).data if active_shift else None
        return Response(payload)


class CategoryListApiView(APIView):
    permission_classes = [IsDirector]

    def get(self, request):
        queryset = Category.objects.all().order_by('name')
        return Response(CategorySerializer(queryset, many=True).data)


class ProductListApiView(APIView):
    def get(self, request):
        queryset = Product.objects.select_related('category').all().order_by('name')
        search = request.query_params.get('search', '').strip()
        category_id = request.query_params.get('category_id', '').strip()

        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        return Response(ProductSerializer(queryset, many=True).data)


class ClientListApiView(APIView):
    permission_classes = [IsDirector]

    def get(self, request):
        queryset = Client.objects.all().order_by('name')
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search) | Q(company__icontains=search)
            )
        return Response(ClientSerializer(queryset, many=True).data)


class SaleListCreateApiView(APIView):
    permission_classes = [IsDirectorOrSeller]

    def get(self, request):
        queryset = Sale.objects.select_related('client', 'seller', 'shift').prefetch_related('items__product')
        if request.user.role == 'seller':
            queryset = queryset.filter(seller=request.user)

        status_param = request.query_params.get('status', '').strip()
        date_from = request.query_params.get('date_from', '').strip()
        date_to = request.query_params.get('date_to', '').strip()
        if status_param:
            queryset = queryset.filter(status=status_param)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return Response(SaleSerializer(queryset.order_by('-created_at'), many=True).data)

    def post(self, request):
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        active_shift = get_active_shift(request.user)
        if request.user.role == 'seller' and not active_shift:
            return Response({'detail': "Sotuv qilish uchun avval smenani boshlang"}, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        items_payload = validated['items']
        client = None

        if request.user.role == 'director' and validated.get('client_id'):
            client = get_object_or_404(Client, pk=validated['client_id'])

        if request.user.role == 'seller' and validated.get('client_id'):
            return Response({'detail': "Sotuvchi API orqali mijoz biriktira olmaydi"}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            product_ids = [item['product_id'] for item in items_payload]
            products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(id__in=product_ids)
            }

            if len(products) != len(set(product_ids)):
                return Response({'detail': 'Tanlangan mahsulotlardan biri topilmadi'}, status=status.HTTP_400_BAD_REQUEST)

            sale = Sale.objects.create(
                client=client,
                seller=request.user,
                shift=active_shift,
                total_amount=0,
                status='pending',
                payment_type='cash',
                notes=validated.get('notes', ''),
            )

            total_amount = 0
            for item in items_payload:
                product = products[item['product_id']]
                quantity = item['quantity']
                if product.stock < quantity:
                    return Response(
                        {'detail': f"{product.name} uchun omborda yetarli qoldiq yo'q"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                line_total = product.price * quantity
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    unit_price=product.price,
                    total_price=line_total,
                )
                product.stock -= quantity
                product.save(update_fields=['stock'])
                WarehouseTransaction.objects.create(
                    product=product,
                    transaction_type='out',
                    quantity=quantity,
                    notes=f'Sotuv #{sale.id} orqali',
                    created_by=request.user,
                )
                total_amount += line_total

            sale.total_amount = total_amount
            sale.status = 'completed'
            sale.save(update_fields=['total_amount', 'status'])

        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class SaleDetailApiView(APIView):
    permission_classes = [IsDirectorOrSeller]

    def get(self, request, pk):
        queryset = Sale.objects.select_related('client', 'seller', 'shift').prefetch_related('items__product')
        if request.user.role == 'seller':
            queryset = queryset.filter(seller=request.user)
        sale = get_object_or_404(queryset, pk=pk)
        return Response(SaleSerializer(sale).data)


class ShiftListApiView(APIView):
    permission_classes = [IsDirectorOrSeller]

    def get(self, request):
        queryset = SellerShift.objects.select_related('seller').all()
        if request.user.role == 'seller':
            queryset = queryset.filter(seller=request.user)
        return Response(SellerShiftSerializer(queryset.order_by('-started_at'), many=True).data)


class CurrentShiftApiView(APIView):
    permission_classes = [IsDirectorOrSeller]

    def get(self, request):
        if request.user.role != 'seller':
            return Response({'detail': 'Joriy smena endpointi faqat sotuvchi uchun'}, status=status.HTTP_403_FORBIDDEN)
        shift = get_active_shift(request.user)
        return Response(SellerShiftSerializer(shift).data if shift else None)


class ShiftStartApiView(APIView):
    permission_classes = [IsDirectorOrSeller]

    def post(self, request):
        if request.user.role != 'seller':
            return Response({'detail': 'Smena boshlash endpointi faqat sotuvchi uchun'}, status=status.HTTP_403_FORBIDDEN)

        active_shift = get_active_shift(request.user)
        if active_shift:
            return Response({'detail': 'Sizda allaqachon ochiq smena mavjud'}, status=status.HTTP_400_BAD_REQUEST)

        shift = SellerShift.objects.create(seller=request.user)
        return Response(SellerShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class ShiftEndApiView(APIView):
    permission_classes = [IsDirectorOrSeller]

    def post(self, request):
        if request.user.role != 'seller':
            return Response({'detail': 'Smena yopish endpointi faqat sotuvchi uchun'}, status=status.HTTP_403_FORBIDDEN)

        shift = get_active_shift(request.user)
        if not shift:
            return Response({'detail': "Yopish uchun ochiq smena topilmadi"}, status=status.HTTP_400_BAD_REQUEST)

        shift.ended_at = timezone.now()
        shift.save(update_fields=['ended_at', 'updated_at'])
        return Response(SellerShiftSerializer(shift).data)


class ShiftReportApiView(APIView):
    permission_classes = [IsDirectorOrSeller]

    def get(self, request, pk):
        queryset = SellerShift.objects.select_related('seller').all()
        if request.user.role == 'seller':
            queryset = queryset.filter(seller=request.user)
        shift = get_object_or_404(queryset, pk=pk)
        report_context = build_shift_report_context(shift)
        payload = {
            'shift': shift,
            'total_sales': report_context['shift_total_sales'],
            'total_quantity': report_context['shift_total_quantity'],
            'total_revenue': report_context['shift_total_revenue'],
            'items': report_context['shift_items'],
        }
        return Response(SellerShiftReportSerializer(payload).data)


class CourierLoginApiView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        user = authenticate(request, username=username, password=password)
        if not user or user.role not in {'supplier', 'courier'}:
            return Response({'detail': "Kuryer login yoki paroli noto'g'ri"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'token': issue_courier_token(user),
                'user': UserSummarySerializer(user).data,
            }
        )


class CourierMeApiView(CourierApiBaseView):
    def get(self, request):
        user, error = self.require_courier(request)
        if error:
            return error

        payload = UserSummarySerializer(user).data
        payload['stats'] = CourierStatsSerializer(
            {
                'available_orders': TelegramOrder.objects.filter(status__in={'new', 'confirmed'}, courier__isnull=True).count(),
                'active_orders': TelegramOrder.objects.filter(status='delivering', courier=user).count(),
                'completed_orders': TelegramOrder.objects.filter(status='completed', courier=user).count(),
            }
        ).data
        return Response(payload)


class CourierDashboardApiView(CourierApiBaseView):
    def get(self, request):
        user, error = self.require_courier(request)
        if error:
            return error

        payload = {
            'available_orders': TelegramOrder.objects.filter(status__in={'new', 'confirmed'}, courier__isnull=True).count(),
            'active_orders': TelegramOrder.objects.filter(status='delivering', courier=user).count(),
            'completed_orders': TelegramOrder.objects.filter(status='completed', courier=user).count(),
        }
        return Response(CourierStatsSerializer(payload).data)


class CourierOrderListApiView(CourierApiBaseView):
    def get(self, request):
        user, error = self.require_courier(request)
        if error:
            return error

        queryset = get_courier_orders_queryset(user)
        status_param = request.query_params.get('status', '').strip()
        if status_param:
            queryset = queryset.filter(status=status_param)

        return Response(CourierOrderSerializer(queryset, many=True).data)


class CourierOrderDetailApiView(CourierApiBaseView):
    def get(self, request, pk):
        user, error = self.require_courier(request)
        if error:
            return error

        order = get_object_or_404(get_courier_orders_queryset(user), pk=pk)
        return Response(CourierOrderSerializer(order).data)


class CourierOrderAcceptApiView(CourierApiBaseView):
    def post(self, request, pk):
        user, error = self.require_courier(request)
        if error:
            return error

        order = get_object_or_404(
            TelegramOrder.objects.select_related('courier', 'profile__user', 'sale').prefetch_related('items__product'),
            pk=pk,
        )
        if order.status != 'confirmed':
            return Response({'detail': 'Faqat tasdiqlangan buyurtmani qabul qilish mumkin'}, status=status.HTTP_400_BAD_REQUEST)
        if order.courier_id and order.courier_id != user.id:
            return Response({'detail': 'Bu buyurtma boshqa kuryerga biriktirilgan'}, status=status.HTTP_403_FORBIDDEN)

        order.courier = user
        order.status = 'delivering'
        order.save(update_fields=['courier', 'status', 'updated_at'])
        notify_order_profile(
            order.profile,
            f"Buyurtmangiz kuryer tomonidan qabul qilindi va yetkazib berilyapti. Buyurtma raqami: #{order.id}.",
        )
        return Response(CourierOrderSerializer(order).data)


class CourierOrderCompleteApiView(CourierApiBaseView):
    def post(self, request, pk):
        user, error = self.require_courier(request)
        if error:
            return error

        order = get_object_or_404(
            TelegramOrder.objects.select_related('courier', 'profile__user', 'sale').prefetch_related('items__product'),
            pk=pk,
            courier=user,
        )
        if order.status != 'delivering':
            return Response({'detail': 'Faqat yetkazilayotgan buyurtmani yakunlash mumkin'}, status=status.HTTP_400_BAD_REQUEST)

        order.status = 'completed'
        order.save(update_fields=['status', 'updated_at'])
        notify_order_profile(
            order.profile,
            f"Buyurtmangiz muvaffaqiyatli yetkazildi. Buyurtma raqami: #{order.id}.",
        )
        return Response(CourierOrderSerializer(order).data)
