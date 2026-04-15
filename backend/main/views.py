import json
from datetime import timedelta
from decimal import Decimal
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import models, transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from .forms import (
    CategoryForm,
    ClientForm,
    LoginForm,
    ProductForm,
    UserChangeForm,
    UserCreationForm,
)
from .models import (
    Category,
    Client,
    Product,
    Sale,
    SaleItem,
    SellerShift,
    TelegramOrder,
    TelegramOrderItem,
    TelegramProfile,
    User,
    WarehouseTransaction,
)
from .telegram_bot import (
    MINI_APP_LAUNCH_TOKEN_SALT,
    bot_enabled,
    process_update,
    send_message,
    validate_init_data,
)


MINI_APP_TOKEN_SALT = 'mini-app-auth'


def user_has_role(user, *roles):
    return user.is_authenticated and user.role in roles


def display_name(user):
    full_name = user.get_full_name().strip()
    return full_name or user.username


def get_catalog_products_queryset():
    return Product.objects.select_related('category').order_by('name')


def serialize_catalog_products(queryset=None):
    queryset = queryset or get_catalog_products_queryset()
    products = list(
        queryset.values(
            'id',
            'name',
            'price',
            'stock',
            'unit',
            'category__name',
            'description',
        )
    )
    for product in products:
        product['is_available'] = product['stock'] > 0
    return products


def get_active_shift(user):
    if not user.is_authenticated or user.role != 'seller':
        return None
    return SellerShift.objects.filter(seller=user, ended_at__isnull=True).order_by('-started_at').first()


def build_shift_report_context(shift):
    sales = shift.sales.filter(status='completed').select_related('client', 'seller').prefetch_related('items__product').order_by('created_at')
    sale_items = SaleItem.objects.filter(
        sale__shift=shift,
        sale__status='completed',
    ).select_related('sale', 'product').order_by('sale__created_at', 'id')
    total_revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    total_quantity = sale_items.aggregate(total=Sum('quantity'))['total'] or 0
    return {
        'shift': shift,
        'shift_sales': sales,
        'shift_items': sale_items,
        'shift_total_revenue': total_revenue,
        'shift_total_sales': sales.count(),
        'shift_total_quantity': total_quantity,
    }


def build_sales_period_stats(start_date, end_date):
    sales = Sale.objects.filter(
        status='completed',
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    aggregated = sales.aggregate(total=Sum('total_amount'), count=Count('id'))
    return {
        'total': aggregated['total'] or Decimal('0'),
        'count': aggregated['count'] or 0,
        'start_date': start_date,
        'end_date': end_date,
    }


def build_change_stats(current_total, previous_total):
    current_total = Decimal(current_total or 0)
    previous_total = Decimal(previous_total or 0)

    if previous_total == 0:
        if current_total == 0:
            return {
                'direction': 'same',
                'percent': Decimal('0.0'),
                'has_baseline': True,
            }
        return {
            'direction': 'up',
            'percent': None,
            'has_baseline': False,
        }

    change_percent = ((current_total - previous_total) / previous_total) * Decimal('100')
    if change_percent > 0:
        direction = 'up'
    elif change_percent < 0:
        direction = 'down'
    else:
        direction = 'same'

    return {
        'direction': direction,
        'percent': abs(change_percent).quantize(Decimal('0.1')),
        'has_baseline': True,
    }


def get_supplier_delivery_queryset(user):
    return TelegramOrder.objects.filter(
        status__in={'confirmed', 'delivering', 'completed'},
    ).select_related('profile__user', 'sale').prefetch_related('items__product').order_by('-created_at')


def issue_mini_app_token(profile):
    payload = {
        'profile_id': profile.id,
        'chat_id': profile.chat_id,
    }
    return signing.dumps(payload, salt=MINI_APP_TOKEN_SALT)


def get_or_create_client_from_order(order):
    client = Client.objects.filter(phone=order.phone).first()
    if client:
        updated = False
        if not client.name:
            client.name = order.full_name
            updated = True
        preferred_address = order.address or order.comment
        if not client.address and preferred_address:
            client.address = preferred_address
            updated = True
        if updated:
            client.save()
        return client

    return Client.objects.create(
        name=order.full_name,
        phone=order.phone,
        address=order.address or order.comment,
    )


def notify_order_profile(profile, text):
    if not profile or not profile.chat_id:
        return
    try:
        send_message(profile.chat_id, text)
    except Exception:
        return


def get_mini_app_profile(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(' ', 1)[1].strip()
    if not token:
        return None

    try:
        payload = signing.loads(token, salt=MINI_APP_TOKEN_SALT, max_age=86400)
    except signing.BadSignature:
        return None

    return TelegramProfile.objects.filter(
        id=payload.get('profile_id'),
        chat_id=payload.get('chat_id'),
        is_active=True,
    ).select_related('user').first()


def get_profile_from_launch_token(launch_token):
    if not launch_token:
        return None

    try:
        payload = signing.loads(launch_token, salt=MINI_APP_LAUNCH_TOKEN_SALT, max_age=7 * 24 * 60 * 60)
    except signing.BadSignature:
        return None

    chat_id = payload.get('chat_id')
    if not chat_id:
        return None

    profile = TelegramProfile.objects.filter(chat_id=chat_id).first()
    if profile:
        profile.chat_username = payload.get('username', '')
        profile.first_name = payload.get('first_name', '')
        profile.last_name = payload.get('last_name', '')
        profile.is_active = True
        profile.save(update_fields=['chat_username', 'first_name', 'last_name', 'is_active', 'last_seen_at'])
        return profile

    return TelegramProfile.objects.create(
        chat_id=chat_id,
        chat_username=payload.get('username', ''),
        first_name=payload.get('first_name', ''),
        last_name=payload.get('last_name', ''),
        is_active=True,
    )


def get_profile_from_telegram_user(telegram_user):
    if not isinstance(telegram_user, dict):
        return None

    chat_id = telegram_user.get('id')
    if not chat_id:
        return None

    profile = TelegramProfile.objects.filter(chat_id=chat_id).first()
    if profile:
        profile.chat_username = telegram_user.get('username', '')
        profile.first_name = telegram_user.get('first_name', '')
        profile.last_name = telegram_user.get('last_name', '')
        profile.is_active = True
        profile.save(update_fields=['chat_username', 'first_name', 'last_name', 'is_active', 'last_seen_at'])
        return profile

    return TelegramProfile.objects.create(
        chat_id=chat_id,
        chat_username=telegram_user.get('username', ''),
        first_name=telegram_user.get('first_name', ''),
        last_name=telegram_user.get('last_name', ''),
        is_active=True,
    )


def create_guest_mini_app_profile():
    # Negative synthetic chat ids avoid clashing with real Telegram chat ids.
    chat_id = -int(time.time() * 1000000)
    return TelegramProfile.objects.create(
        chat_id=chat_id,
        chat_username='guest',
        first_name='Guest',
        last_name='MiniApp',
        is_active=True,
    )


def apply_sale_status_change(sale, new_status, actor):
    valid_statuses = {choice[0] for choice in Sale.STATUS_CHOICES}
    if new_status not in valid_statuses:
        return False, "Noto'g'ri status tanlandi"

    if sale.status == new_status:
        return True, None

    with transaction.atomic():
        items = list(sale.items.select_related('product'))
        locked_products = {
            product.id: product
            for product in Product.objects.select_for_update().filter(
                id__in=[item.product_id for item in items]
            )
        }

        if sale.status == 'completed' and new_status in {'cancelled', 'returned'}:
            note = f"Sotuv #{sale.id} holati {new_status} ga o'zgartirildi"
            for item in items:
                product = locked_products[item.product_id]
                product.stock += item.quantity
                product.save(update_fields=['stock'])
                WarehouseTransaction.objects.create(
                    product=product,
                    transaction_type='in',
                    quantity=item.quantity,
                    notes=note,
                    created_by=actor,
                )
        elif sale.status in {'pending', 'cancelled', 'returned'} and new_status == 'completed':
            for item in items:
                product = locked_products[item.product_id]
                if product.stock < item.quantity:
                    return False, f"{product.name} uchun omborda yetarli qoldiq yo'q"

            for item in items:
                product = locked_products[item.product_id]
                product.stock -= item.quantity
                product.save(update_fields=['stock'])
                WarehouseTransaction.objects.create(
                    product=product,
                    transaction_type='out',
                    quantity=item.quantity,
                    notes=f'Sotuv #{sale.id} qayta yakunlandi',
                    created_by=actor,
                )

        sale.status = new_status
        sale.save(update_fields=['status'])

    return True, None


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
            messages.error(request, "Foydalanuvchi nomi yoki parol noto'g'ri")
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def kassa(request):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    active_shift = get_active_shift(request.user)
    products = Product.objects.filter(stock__gt=0).select_related('category')
    return render(request, 'kassa.html', {'products': products, 'active_shift': active_shift})


@login_required
@require_POST
def kassa_checkout(request):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    active_shift = get_active_shift(request.user)
    if not active_shift:
        messages.error(request, "Avval smenani boshlang")
        return redirect('dashboard')

    payment_type = request.POST.get('payment_type', 'cash').strip()
    valid_payment_types = {choice[0] for choice in Sale.PAYMENT_TYPE_CHOICES}
    if payment_type not in valid_payment_types:
        messages.error(request, "To'lov turi noto'g'ri tanlandi")
        return redirect('kassa')

    product_ids = request.POST.getlist('product_id[]')
    quantities = request.POST.getlist('quantity[]')
    if not product_ids or not quantities or len(product_ids) != len(quantities):
        messages.error(request, "Savat bo'sh yoki noto'g'ri yuborilgan")
        return redirect('kassa')

    cart_lines = []
    for product_id, quantity in zip(product_ids, quantities):
        try:
            parsed_product_id = int(product_id)
            parsed_quantity = int(quantity)
        except (TypeError, ValueError):
            messages.error(request, "Savatdagi mahsulot ma'lumoti noto'g'ri")
            return redirect('kassa')

        if parsed_quantity < 1:
            messages.error(request, "Mahsulot soni 1 dan kichik bo'lishi mumkin emas")
            return redirect('kassa')
        cart_lines.append((parsed_product_id, parsed_quantity))

    with transaction.atomic():
        locked_products = {
            product.id: product
            for product in Product.objects.select_for_update().filter(
                id__in=[product_id for product_id, _ in cart_lines]
            )
        }
        if len(locked_products) != len({product_id for product_id, _ in cart_lines}):
            messages.error(request, "Tanlangan mahsulotlardan biri topilmadi")
            return redirect('kassa')

        for product_id, quantity in cart_lines:
            product = locked_products[product_id]
            if product.stock < quantity:
                messages.error(request, f"{product.name} uchun yetarli mahsulot yo'q")
                return redirect('kassa')

        sale = Sale.objects.create(
            client=None,
            seller=request.user,
            shift=active_shift,
            total_amount=Decimal('0'),
            status='completed',
            payment_type=payment_type,
        )

        total_amount = Decimal('0')
        for product_id, quantity in cart_lines:
            product = locked_products[product_id]
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
                notes=f"Sotuv #{sale.id} ({sale.get_payment_type_display()}) orqali",
                created_by=request.user,
            )
            total_amount += line_total

        sale.total_amount = total_amount
        sale.save(update_fields=['total_amount'])

    messages.success(
        request,
        f"Sotuv #{sale.id} muvaffaqiyatli yakunlandi. To'lov turi: {sale.get_payment_type_display()}",
    )
    return redirect('sale_detail', pk=sale.pk)


@login_required
def kassa_sell(request, product_id):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    product = get_object_or_404(Product, pk=product_id)
    active_shift = get_active_shift(request.user)

    if request.method == 'POST':
        if not active_shift:
            messages.error(request, "Avval smenani boshlang")
            return redirect('dashboard')

        quantity = int(request.POST.get('quantity', 1))
        if quantity < 1:
            messages.error(request, "Sotuv Soni 1 dan kichik bo'lishi mumkin emas")
            return redirect('kassa_sell', product_id=product_id)

        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product.pk)
            if product.stock < quantity:
                messages.error(request, f"{product.name} uchun yetarli mahsulot yo'q")
                return redirect('kassa')

            total = product.price * quantity
            sale = Sale.objects.create(
                client=None,
                seller=request.user,
                shift=active_shift,
                total_amount=total,
                status='completed',
                payment_type='cash',
            )

            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=product.price,
                total_price=total,
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

        messages.success(request, f'{product.name} - {quantity} {product.unit} sotildi!')
        return redirect('kassa')

    return render(request, 'kassa_sell.html', {'product': product})


@login_required
def dashboard(request):
    context = {}
    user_role = request.user.role
    today = timezone.now().date()

    if user_role == 'director':
        active_deliveries_count = TelegramOrder.objects.filter(status__in={'confirmed', 'delivering'}).count()
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=today.weekday())
        previous_week_start = week_start - timedelta(days=7)
        previous_week_end = week_start - timedelta(days=1)
        month_start = today.replace(day=1)
        previous_month_end = month_start - timedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)

        daily_stats = build_sales_period_stats(today, today)
        previous_daily_stats = build_sales_period_stats(yesterday, yesterday)
        weekly_stats = build_sales_period_stats(week_start, today)
        previous_weekly_stats = build_sales_period_stats(previous_week_start, previous_week_end)
        monthly_stats = build_sales_period_stats(month_start, today)
        previous_monthly_stats = build_sales_period_stats(previous_month_start, previous_month_end)

        cash_revenue = Sale.objects.filter(
            status='completed',
            payment_type='cash',
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        card_revenue = Sale.objects.filter(
            status='completed',
            payment_type='card',
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        context['active_deliveries_count'] = active_deliveries_count
        context['daily_stats'] = daily_stats
        context['daily_change'] = build_change_stats(daily_stats['total'], previous_daily_stats['total'])
        context['weekly_stats'] = weekly_stats
        context['weekly_change'] = build_change_stats(weekly_stats['total'], previous_weekly_stats['total'])
        context['monthly_stats'] = monthly_stats
        context['monthly_change'] = build_change_stats(monthly_stats['total'], previous_monthly_stats['total'])
        context['cash_revenue'] = cash_revenue
        context['card_revenue'] = card_revenue
        context['top_products'] = SaleItem.objects.filter(
            sale__status='completed',
        ).values(
            'product__name',
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_price'),
        ).order_by('-total_quantity', '-total_revenue', 'product__name')[:10]
    elif user_role == 'seller':
        active_shift = get_active_shift(request.user)
        last_closed_shift = SellerShift.objects.filter(
            seller=request.user,
            ended_at__isnull=False,
        ).order_by('-ended_at').first()
        context['my_sales'] = Sale.objects.filter(seller=request.user).count()
        context['today_sales'] = Sale.objects.filter(seller=request.user, created_at__date=today).count()
        context['my_revenue'] = Sale.objects.filter(
            seller=request.user, status='completed'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        context['recent_sales'] = Sale.objects.filter(seller=request.user).select_related(
            'client'
        ).order_by('-created_at')[:10]
        context['active_shift'] = active_shift
        context['last_closed_shift'] = last_closed_shift
    elif user_role == 'warehouse':
        context['total_products'] = Product.objects.count()
        context['low_stock'] = Product.objects.filter(stock__lt=10).count()
        context['total_stock'] = Product.objects.aggregate(Sum('stock'))['stock__sum'] or 0
        context['recent_transactions'] = WarehouseTransaction.objects.select_related(
            'product', 'created_by'
        ).order_by('-created_at')[:10]
    elif user_role == 'supplier':
        supplier_orders = get_supplier_delivery_queryset(request.user)
        context['pending_deliveries'] = supplier_orders.filter(status='confirmed').count()
        context['completed_deliveries'] = supplier_orders.filter(status='completed').count()
        context['delivery_revenue'] = supplier_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        context['recent_orders'] = supplier_orders[:10]

    return render(request, 'dashboard.html', context)


@login_required
def users_list(request):
    if request.user.role != 'director':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    users = User.objects.all()
    active_shift_map = {
        shift.seller_id: shift
        for shift in SellerShift.objects.filter(ended_at__isnull=True).select_related('seller')
    }
    for user in users:
        user.active_shift = active_shift_map.get(user.id)
    return render(request, 'users.html', {'users': users})


@login_required
def user_create(request):
    if request.user.role != 'director':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = request.POST.get('role', 'seller')
            user.save()
            messages.success(request, f'{user.username} foydalanuvchi muvaffaqiyatli yaratildi')
            return redirect('users')
    else:
        form = UserCreationForm()
    return render(request, 'user_form.html', {'form': form, 'action': 'create'})


@login_required
def user_edit(request, pk):
    if request.user.role != 'director':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserChangeForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save(commit=False)
            if request.POST.get('password'):
                user.set_password(request.POST.get('password'))
            user.save()
            messages.success(request, 'Foydalanuvchi muvaffaqiyatli yangilandi')
            return redirect('users')
    else:
        form = UserChangeForm(instance=user)
    return render(request, 'user_form.html', {'form': form, 'action': 'edit', 'user': user})


@login_required
def user_delete(request, pk):
    if request.user.role != 'director':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, "O'zingizni o'chira olmaysiz")
    else:
        user.delete()
        messages.success(request, "Foydalanuvchi o'chirildi")
    return redirect('users')


@login_required
def categories_list(request):
    if request.user.role in {'director', 'seller', 'supplier'}:
        messages.error(request, "Siz uchun kategoriyalar bo'limi yopilgan")
        return redirect('dashboard')

    categories = Category.objects.annotate(product_count=Count('products'))
    return render(request, 'categories.html', {'categories': categories})


@login_required
def category_create(request):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kategoriya muvaffaqiyatli yaratildi')
            return redirect('categories')
    else:
        form = CategoryForm()
    return render(request, 'category_form.html', {'form': form, 'action': 'create'})


@login_required
def category_edit(request, pk):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kategoriya muvaffaqiyatli yangilandi')
            return redirect('categories')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'category_form.html', {'form': form, 'action': 'edit', 'category': category})


@login_required
def category_delete(request, pk):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    category = get_object_or_404(Category, pk=pk)
    category.delete()
    messages.success(request, "Kategoriya o'chirildi")
    return redirect('categories')


@login_required
def products_list(request):
    if request.user.role in {'director', 'seller', 'supplier'}:
        messages.error(request, "Siz uchun mahsulotlar bo'limi yopilgan")
        return redirect('dashboard')

    search = request.GET.get('search', '')
    category_id = request.GET.get('category', '')

    products = get_catalog_products_queryset()

    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if category_id:
        products = products.filter(category_id=category_id)

    categories = Category.objects.all()
    return render(request, 'products.html', {'products': products, 'categories': categories})


@login_required
def product_create(request):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Mahsulot muvaffaqiyatli yaratildi')
            return redirect('products')
    else:
        form = ProductForm()
    return render(request, 'product_form.html', {'form': form, 'action': 'create'})


@login_required
def product_edit(request, pk):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Mahsulot muvaffaqiyatli yangilandi')
            return redirect('products')
    else:
        form = ProductForm(instance=product)
    return render(request, 'product_form.html', {'form': form, 'action': 'edit', 'product': product})


@login_required
def product_delete(request, pk):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.success(request, "Mahsulot o'chirildi")
    return redirect('products')


@login_required
def product_detail(request, pk):
    if request.user.role in {'director', 'seller', 'supplier'}:
        messages.error(request, "Siz uchun mahsulotlar bo'limi yopilgan")
        return redirect('dashboard')

    product = get_object_or_404(Product.objects.select_related('category'), pk=pk)
    transactions = product.transactions.order_by('-created_at')[:10]
    return render(request, 'product_detail.html', {'product': product, 'transactions': transactions})


@login_required
def clients_list(request):
    if request.user.role in {'director', 'seller', 'warehouse', 'supplier'}:
        messages.error(request, "Siz uchun mijozlar ro'yxati yopilgan")
        return redirect('dashboard')

    search = request.GET.get('search', '')
    clients = Client.objects.all()
    if search:
        clients = clients.filter(
            Q(name__icontains=search) | Q(phone__icontains=search) | Q(company__icontains=search)
        )
    return render(request, 'clients.html', {'clients': clients})


@login_required
def client_create(request):
    messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
    return redirect('dashboard')

    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Mijoz muvaffaqiyatli yaratildi')
            return redirect('clients')
    else:
        form = ClientForm()
    return render(request, 'client_form.html', {'form': form, 'action': 'create'})


@login_required
def client_edit(request, pk):
    messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
    return redirect('dashboard')

    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, 'Mijoz muvaffaqiyatli yangilandi')
            return redirect('clients')
    else:
        form = ClientForm(instance=client)
    return render(request, 'client_form.html', {'form': form, 'action': 'edit', 'client': client})


@login_required
def client_delete(request, pk):
    messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
    return redirect('dashboard')

    client = get_object_or_404(Client, pk=pk)
    client.delete()
    messages.success(request, "Mijoz o'chirildi")
    return redirect('clients')


@login_required
def client_detail(request, pk):
    if request.user.role in {'director', 'seller', 'warehouse', 'supplier'}:
        messages.error(request, "Siz uchun mijozlar ro'yxati yopilgan")
        return redirect('dashboard')

    client = get_object_or_404(Client, pk=pk)
    sales = client.sales.select_related('seller').order_by('-created_at')[:20]
    total_spent = client.sales.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    return render(request, 'client_detail.html', {'client': client, 'sales': sales, 'total_spent': total_spent})


@login_required
def sales_list(request):
    if request.user.role in {'warehouse', 'supplier'}:
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    sales = Sale.objects.select_related('client', 'seller')

    active_shift = None
    if request.user.role == 'seller':
        sales = sales.filter(seller=request.user)
        active_shift = get_active_shift(request.user)

    if status:
        sales = sales.filter(status=status)
    if date_from:
        sales = sales.filter(created_at__date__gte=date_from)
    if date_to:
        sales = sales.filter(created_at__date__lte=date_to)

    sales = sales.order_by('-created_at')
    return render(request, 'sales.html', {'sales': sales, 'active_shift': active_shift})


@login_required
def sale_create(request):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    active_shift = get_active_shift(request.user)
    if request.user.role == 'seller' and not active_shift:
        messages.error(request, "Sotuv qilish uchun avval smenani boshlang")
        return redirect('dashboard')

    if request.method == 'POST':
        client_id = request.POST.get('client')
        notes = request.POST.get('notes', '').strip()
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')

        client = None
        if client_id:
            client = get_object_or_404(Client, pk=client_id)

        sale_lines = []
        for pid, qty in zip(product_ids, quantities):
            if not pid or not qty:
                continue
            quantity = int(qty)
            if quantity < 1:
                messages.error(request, "Mahsulot Soni 1 dan kichik bo'lishi mumkin emas")
                return redirect('sale_create')
            sale_lines.append((int(pid), quantity))

        if not sale_lines:
            messages.error(request, "Kamida bitta mahsulot tanlashingiz kerak")
            return redirect('sale_create')

        with transaction.atomic():
            locked_products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(
                    id__in=[product_id for product_id, _ in sale_lines]
                )
            }
            unique_product_ids = {product_id for product_id, _ in sale_lines}
            if len(locked_products) != len(unique_product_ids):
                messages.error(request, "Tanlangan mahsulotlardan biri topilmadi")
                return redirect('sale_create')

            sale = Sale.objects.create(
                client=client,
                seller=request.user,
                shift=active_shift,
                total_amount=0,
                notes=notes,
                status='pending',
                payment_type='cash',
            )

            total = 0
            for product_id, quantity in sale_lines:
                product = locked_products[product_id]
                if product.stock < quantity:
                    messages.error(request, f"{product.name} uchun yetarli mahsulot yo'q")
                    transaction.set_rollback(True)
                    return redirect('sale_create')

                unit_price = product.price
                item_total = unit_price * quantity
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=item_total,
                )
                total += item_total
                product.stock -= quantity
                product.save(update_fields=['stock'])
                WarehouseTransaction.objects.create(
                    product=product,
                    transaction_type='out',
                    quantity=quantity,
                    notes=f'Sotuv #{sale.id} orqali',
                    created_by=request.user,
                )

            sale.total_amount = total
            sale.status = 'completed'
            sale.save(update_fields=['total_amount', 'status'])

        messages.success(request, f'Sotuv #{sale.id} muvaffaqiyatli yaratildi')
        return redirect('sales')

    clients = Client.objects.none()
    products = Product.objects.filter(stock__gt=0)
    return render(
        request,
        'sale_form.html',
        {'clients': clients, 'products': products, 'action': 'create', 'active_shift': active_shift},
    )


@login_required
def sale_detail(request, pk):
    if request.user.role == 'supplier':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    sale = get_object_or_404(Sale.objects.select_related('client', 'seller'), pk=pk)
    items = sale.items.select_related('product')
    return render(request, 'sale_detail.html', {'sale': sale, 'items': items})


@login_required
def sale_update_status(request, pk):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    if request.method == 'POST':
        sale = get_object_or_404(Sale, pk=pk)
        new_status = request.POST.get('status')
        success, error_message = apply_sale_status_change(sale, new_status, request.user)
        if not success:
            messages.error(request, error_message)
        else:
            messages.success(request, 'Sotuv holati yangilandi')
    return redirect('sale_detail', pk=pk)


@login_required
def warehouse(request):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    search = request.GET.get('search', '')
    products = Product.objects.select_related('category')

    if search:
        products = products.filter(name__icontains=search)

    return render(request, 'warehouse.html', {'products': products})


@login_required
def warehouse_transaction(request):
    if request.user.role != 'warehouse':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    if request.method == 'POST':
        product_id = request.POST.get('product')
        transaction_type = request.POST.get('transaction_type', 'in')
        quantity = int(request.POST.get('quantity', 0))
        notes = request.POST.get('notes', '')

        if product_id and quantity > 0 and transaction_type in {'in', 'out'}:
            with transaction.atomic():
                product = Product.objects.select_for_update().get(pk=product_id)
                if transaction_type == 'out' and product.stock < quantity:
                    messages.error(request, f"{product.name} uchun omborda yetarli qoldiq yo'q")
                    return redirect('warehouse_transaction')

                if transaction_type == 'in':
                    product.stock += quantity
                else:
                    product.stock -= quantity
                product.save(update_fields=['stock'])

                WarehouseTransaction.objects.create(
                    product=product,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    notes=notes,
                    created_by=request.user,
                )

            action_text = "qo'shildi" if transaction_type == 'in' else "chiqarildi"
            messages.success(request, f"{product.name} uchun {quantity} {product.unit} {action_text}!")
            return redirect('warehouse')

        messages.error(request, "Operatsiya uchun to'g'ri ma'lumot kiriting")

    products = Product.objects.all()
    return render(request, 'transaction_form.html', {'products': products})


@login_required
def transactions_history(request):
    if request.user.role != 'director':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    transactions = WarehouseTransaction.objects.select_related('product', 'created_by').order_by('-created_at')
    return render(request, 'transactions.html', {'transactions': transactions})


@login_required
def reports(request):
    if request.user.role not in {'director', 'seller'}:
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    if request.user.role == 'seller':
        active_shift = get_active_shift(request.user)
        shifts = SellerShift.objects.filter(seller=request.user).order_by('-started_at')
        context = {
            'active_shift': active_shift,
            'closed_shifts': shifts.filter(ended_at__isnull=False),
        }
        if active_shift:
            context.update(build_shift_report_context(active_shift))
        return render(request, 'reports.html', context)

    total_revenue = Sale.objects.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_sales = Sale.objects.filter(status='completed').count()
    total_clients = Client.objects.count()
    total_products = Product.objects.count()

    sales_by_month = Sale.objects.filter(status='completed').extra(
        select={'month': "strftime('%%Y-%%m', created_at)"}
    ).values('month').annotate(total=Sum('total_amount')).order_by('month')

    top_sellers = User.objects.filter(role='seller').annotate(
        sales_count=Count('sales'),
        total_sales=Sum('sales__total_amount', filter=models.Q(sales__status='completed')),
    ).order_by('-total_sales')[:5]

    seller_rows = [
        {
            'name': display_name(seller),
            'sales_count': seller.sales_count,
            'total_sales': seller.total_sales or 0,
        }
        for seller in top_sellers
    ]

    top_products = SaleItem.objects.values('product__name').annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum('total_price'),
    ).order_by('-total_revenue')[:10]

    context = {
        'total_revenue': total_revenue,
        'total_sales': total_sales,
        'total_clients': total_clients,
        'total_products': total_products,
        'sales_by_month': sales_by_month,
        'top_sellers': seller_rows,
        'top_products': top_products,
    }
    return render(request, 'reports.html', context)


@login_required
@require_POST
def shift_start(request):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    active_shift = get_active_shift(request.user)
    if active_shift:
        messages.info(request, "Sizda allaqachon ochiq smena mavjud")
        return redirect('dashboard')

    shift = SellerShift.objects.create(seller=request.user)
    messages.success(request, f"Smena boshlandi: {shift.started_at:%d.%m.%Y %H:%M}")
    return redirect('dashboard')


@login_required
@require_POST
def seller_shift_start(request, pk):
    if request.user.role != 'director':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    seller = get_object_or_404(User, pk=pk, role='seller')
    active_shift = get_active_shift(seller)
    if active_shift:
        messages.info(request, f"{display_name(seller)} uchun allaqachon ochiq smena mavjud")
        return redirect('users')

    shift = SellerShift.objects.create(seller=seller)
    messages.success(request, f"{display_name(seller)} uchun smena boshlandi: {shift.started_at:%d.%m.%Y %H:%M}")
    return redirect('users')


@login_required
@require_POST
def shift_end(request):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    shift = get_active_shift(request.user)
    if not shift:
        messages.error(request, "Yopish uchun ochiq smena topilmadi")
        return redirect('dashboard')

    shift.ended_at = timezone.now()
    shift.save(update_fields=['ended_at', 'updated_at'])
    messages.success(request, "Smena yopildi")
    return redirect('shift_report', pk=shift.pk)


@login_required
@require_POST
def seller_shift_end(request, pk):
    if request.user.role != 'director':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    seller = get_object_or_404(User, pk=pk, role='seller')
    shift = get_active_shift(seller)
    if not shift:
        messages.error(request, f"{display_name(seller)} uchun ochiq smena topilmadi")
        return redirect('users')

    shift.ended_at = timezone.now()
    shift.save(update_fields=['ended_at', 'updated_at'])
    messages.success(request, f"{display_name(seller)} uchun smena yopildi")
    return redirect('shift_report', pk=shift.pk)


@login_required
def shift_report(request, pk):
    if request.user.role not in {'seller', 'director'}:
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    shift_queryset = SellerShift.objects.all()
    if request.user.role == 'seller':
        shift_queryset = shift_queryset.filter(seller=request.user)
    shift = get_object_or_404(shift_queryset, pk=pk)
    context = build_shift_report_context(shift)
    return render(request, 'shift_report.html', context)


@login_required
def telegram_orders_list(request):
    if not user_has_role(request.user, 'director', 'seller', 'supplier'):
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    status = request.GET.get('status', '')
    orders = TelegramOrder.objects.select_related('profile__user', 'sale').order_by('-created_at')
    if request.user.role == 'supplier':
        orders = orders.filter(status__in={'confirmed', 'delivering', 'completed'})
    if status:
        orders = orders.filter(status=status)

    return render(request, 'telegram_orders.html', {'orders': orders})


@login_required
def telegram_order_detail(request, pk):
    if not user_has_role(request.user, 'director', 'seller', 'supplier'):
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    order = get_object_or_404(
        TelegramOrder.objects.select_related('profile__user', 'sale').prefetch_related('items__product'),
        pk=pk,
    )
    return render(request, 'telegram_order_detail.html', {'order': order})


@login_required
def telegram_order_update_status(request, pk):
    if request.user.role != 'seller':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    order = get_object_or_404(
        TelegramOrder.objects.select_related('sale').prefetch_related('items__product'),
        pk=pk,
    )
    if request.method != 'POST':
        return redirect('telegram_order_detail', pk=pk)

    new_status = request.POST.get('status')
    if new_status not in dict(TelegramOrder.STATUS_CHOICES):
        messages.error(request, "Noto'g'ri status tanlandi")
        return redirect('telegram_order_detail', pk=pk)

    if order.status == new_status:
        messages.info(request, "Buyurtma holati o'zgarmadi")
        return redirect('telegram_order_detail', pk=pk)

    if new_status == 'confirmed':
        active_shift = get_active_shift(request.user)
        if request.user.role == 'seller' and not active_shift:
            messages.error(request, "Buyurtmani tasdiqlash uchun avval smenani boshlang")
            return redirect('telegram_order_detail', pk=pk)

        if order.sale_id:
            order.status = 'confirmed'
            order.save(update_fields=['status'])
            messages.success(request, "Buyurtma tasdiqlangan")
            return redirect('telegram_order_detail', pk=pk)

        with transaction.atomic():
            items = list(order.items.select_related('product'))
            products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(
                    id__in=[item.product_id for item in items]
                )
            }
            for item in items:
                product = products[item.product_id]
                if product.stock < item.quantity:
                    messages.error(request, f"{product.name} uchun omborda yetarli qoldiq yo'q")
                    return redirect('telegram_order_detail', pk=pk)

            client = get_or_create_client_from_order(order)
            sale = Sale.objects.create(
                client=client,
                seller=request.user,
                shift=active_shift,
                total_amount=order.total_amount,
                status='completed',
                payment_type='cash',
                notes=f"Telegram order #{order.id}. {order.comment}".strip(),
            )

            for item in items:
                product = products[item.product_id]
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                )
                product.stock -= item.quantity
                product.save(update_fields=['stock'])
                WarehouseTransaction.objects.create(
                    product=product,
                    transaction_type='out',
                    quantity=item.quantity,
                    notes=f'Telegram order #{order.id} tasdiqlandi',
                    created_by=request.user,
                )

            order.sale = sale
            order.status = 'confirmed'
            order.save(update_fields=['sale', 'status'])

        notify_order_profile(
            order.profile,
            f"Buyurtmangiz qabul qilindi. Buyurtma raqami: #{order.id}. Tez orada yetkazib beruvchi siz bilan bog'lanadi.",
        )
        messages.success(request, "Buyurtma tasdiqlandi va sotuv yaratildi")
        return redirect('telegram_order_detail', pk=pk)

    if new_status == 'cancelled':
        if order.sale_id and order.sale.status == 'completed':
            success, error_message = apply_sale_status_change(order.sale, 'cancelled', request.user)
            if not success:
                messages.error(request, error_message)
                return redirect('telegram_order_detail', pk=pk)
        order.status = 'cancelled'
        order.save(update_fields=['status'])
        messages.success(request, "Buyurtma bekor qilindi")
        return redirect('telegram_order_detail', pk=pk)

    order.status = new_status
    order.save(update_fields=['status'])
    messages.success(request, "Buyurtma holati yangilandi")
    return redirect('telegram_order_detail', pk=pk)


@login_required
def get_product_price(request):
    product_id = request.GET.get('product_id')
    try:
        product = Product.objects.get(pk=product_id)
        return JsonResponse(
            {
                'price': str(product.price),
                'stock': product.stock,
                'unit': product.unit,
            }
        )
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Mahsulot topilmadi'}, status=404)


@login_required
def product_select(request):
    products = serialize_catalog_products(
        get_catalog_products_queryset().only('id', 'name', 'price', 'stock', 'unit', 'category', 'description')
    )
    return JsonResponse(products, safe=False)


@login_required
def supplier_deliveries(request):
    if request.user.role != 'supplier':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    status = request.GET.get('status', '')
    orders = get_supplier_delivery_queryset(request.user)
    if status:
        orders = orders.filter(status=status)
    return render(request, 'supplier_deliveries.html', {'orders': orders})


@login_required
def supplier_legacy_redirect(request):
    if request.user.role != 'supplier':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    return redirect('supplier_deliveries')


@login_required
def supplier_delivery_detail(request, pk):
    if request.user.role != 'supplier':
        messages.error(request, "Sizga bu sahifaga kirish ruxsati yo'q")
        return redirect('dashboard')

    order = get_object_or_404(get_supplier_delivery_queryset(request.user), pk=pk)
    return render(request, 'supplier_delivery_detail.html', {'order': order})


@login_required
@require_POST
def supplier_delivery_complete(request, pk):
    if request.user.role != 'supplier':
        messages.error(request, "Sizga bu amal uchun ruxsat yo'q")
        return redirect('dashboard')

    order = get_object_or_404(get_supplier_delivery_queryset(request.user), pk=pk)
    if order.status == 'confirmed':
        order.status = 'delivering'
        order.save(update_fields=['status'])
        notify_order_profile(
            order.profile,
            f"Buyurtmangiz qabul qilindi va mahsulot yetkazib berilyapti. Buyurtma raqami: #{order.id}.",
        )
        messages.success(request, "Buyurtma yetkazib berish jarayoniga o'tdi")
        return redirect('supplier_delivery_detail', pk=pk)

    if order.status != 'delivering':
        messages.info(request, "Bu buyurtma allaqachon yetkazib bo'lingan")
        return redirect('supplier_delivery_detail', pk=pk)

    order.status = 'completed'
    order.save(update_fields=['status'])
    notify_order_profile(
        order.profile,
        f"Buyurtmangiz muvaffaqiyatli yetkazildi. Buyurtma raqami: #{order.id}.",
    )
    messages.success(request, "Buyurtma mijozga yetkazildi")
    return redirect('supplier_delivery_detail', pk=pk)


@require_GET
def mini_app(request):
    return render(request, 'mini_app.html', {'telegram_bot_name': 'Medical CRM Bot'})


@require_GET
def mini_app_catalog(request):
    return JsonResponse(
        {
            'ok': True,
            'products': serialize_catalog_products(),
        }
    )


@require_POST
@csrf_exempt
def mini_app_auth(request):
    if not bot_enabled():
        return JsonResponse({'ok': False, 'error': 'Bot sozlanmagan'}, status=503)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': "Noto'g'ri JSON"}, status=400)

    init_data = (payload.get('initData') or '').strip()
    launch_token = (payload.get('launchToken') or '').strip()
    telegram_user = payload.get('telegramUser')

    profile = None
    if init_data:
        validated = validate_init_data(init_data)
        if validated:
            tg_user = validated['user']
            profile = TelegramProfile.objects.filter(chat_id=tg_user['id']).first()
            if profile:
                profile.chat_username = tg_user.get('username', '')
                profile.first_name = tg_user.get('first_name', '')
                profile.last_name = tg_user.get('last_name', '')
                profile.is_active = True
                profile.save(update_fields=['chat_username', 'first_name', 'last_name', 'is_active', 'last_seen_at'])
            else:
                profile = TelegramProfile.objects.create(
                    chat_id=tg_user['id'],
                    chat_username=tg_user.get('username', ''),
                    first_name=tg_user.get('first_name', ''),
                    last_name=tg_user.get('last_name', ''),
                    is_active=True,
                )
        elif launch_token:
            profile = get_profile_from_launch_token(launch_token)
        elif telegram_user:
            profile = get_profile_from_telegram_user(telegram_user)
        else:
            return JsonResponse({'ok': False, 'error': 'Telegram autentifikatsiya xatosi'}, status=403)
    elif launch_token:
        profile = get_profile_from_launch_token(launch_token)
    elif telegram_user:
        profile = get_profile_from_telegram_user(telegram_user)
    else:
        profile = create_guest_mini_app_profile()

    if not profile:
        return JsonResponse({'ok': False, 'error': 'Telegram sessiyasi yaroqsiz. Bot ichidan qayta oching.'}, status=403)

    products = serialize_catalog_products()
    token = issue_mini_app_token(profile)
    return JsonResponse(
        {
            'ok': True,
            'token': token,
            'profile': {
                'chat_id': profile.chat_id,
                'chat_username': profile.chat_username,
                'linked_user': profile.user.username if profile.user else None,
                'is_guest': profile.chat_id < 0,
            },
            'products': products,
            'orders': [
                {
                    'id': order.id,
                    'status': order.status,
                    'status_display': order.get_status_display(),
                    'total_amount': str(order.total_amount),
                    'created_at': order.created_at.isoformat(),
                    'sale_id': order.sale_id,
                }
                for order in profile.orders.select_related('sale').order_by('-created_at')[:20]
            ],
        }
    )


@require_POST
@csrf_exempt
def mini_app_create_order(request):
    profile = get_mini_app_profile(request)
    if not profile:
        return JsonResponse({'ok': False, 'error': 'Autentifikatsiya topilmadi'}, status=401)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': "Noto'g'ri JSON"}, status=400)

    customer_name = (payload.get('full_name') or '').strip()
    phone = (payload.get('phone') or '').strip()
    address = (payload.get('address') or '').strip()
    comment = (payload.get('comment') or '').strip()
    location = payload.get('location') or {}
    items = payload.get('items') or []

    if not customer_name or not phone or not address:
        return JsonResponse({'ok': False, 'error': 'Ism, telefon va manzil majburiy'}, status=400)
    if not isinstance(items, list) or not items:
        return JsonResponse({'ok': False, 'error': "Savat bo'sh"}, status=400)

    latitude = None
    longitude = None
    if location:
        try:
            latitude = round(float(location.get('latitude')), 6)
            longitude = round(float(location.get('longitude')), 6)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': "Lokatsiya ma'lumoti noto'g'ri"}, status=400)

    normalized_items = []
    for item in items:
        try:
            product_id = int(item.get('product_id'))
            quantity = int(item.get('quantity'))
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': "Mahsulot ma'lumoti noto'g'ri"}, status=400)
        if quantity < 1:
            return JsonResponse({'ok': False, 'error': "Soni 1 dan kichik bo'lishi mumkin emas"}, status=400)
        normalized_items.append((product_id, quantity))

    with transaction.atomic():
        products = {
            product.id: product
            for product in Product.objects.select_for_update().filter(
                id__in=[product_id for product_id, _ in normalized_items]
            )
        }
        if len(products) != len({product_id for product_id, _ in normalized_items}):
            return JsonResponse({'ok': False, 'error': 'Mahsulot topilmadi'}, status=400)

        for product_id, quantity in normalized_items:
            product = products[product_id]
            if product.stock < quantity:
                return JsonResponse(
                    {'ok': False, 'error': f"{product.name} uchun omborda yetarli qoldiq yo'q"},
                    status=400,
                )

        order = TelegramOrder.objects.create(
            profile=profile,
            full_name=customer_name,
            phone=phone,
            address=address,
            location_latitude=latitude,
            location_longitude=longitude,
            comment=comment,
            status='new',
            total_amount=0,
        )
        total_amount = 0
        for product_id, quantity in normalized_items:
            product = products[product_id]
            line_total = product.price * quantity
            TelegramOrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.price,
                total_price=line_total,
            )
            total_amount += line_total

        order.total_amount = total_amount
        order.save(update_fields=['total_amount'])

    return JsonResponse({'ok': True, 'order_id': order.id, 'total_amount': str(order.total_amount)})


@require_GET
@csrf_exempt
def mini_app_orders(request):
    profile = get_mini_app_profile(request)
    if not profile:
        return JsonResponse({'ok': False, 'error': 'Autentifikatsiya topilmadi'}, status=401)

    orders = [
        {
            'id': order.id,
            'status': order.status,
            'status_display': order.get_status_display(),
            'comment': order.comment,
            'address': order.address,
            'location': {
                'latitude': str(order.location_latitude),
                'longitude': str(order.location_longitude),
            } if order.location_latitude is not None and order.location_longitude is not None else None,
            'total_amount': str(order.total_amount),
            'created_at': order.created_at.isoformat(),
            'sale_id': order.sale_id,
            'items': [
                {
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'total_price': str(item.total_price),
                }
                for item in order.items.select_related('product').all()
            ],
        }
        for order in profile.orders.select_related('sale').prefetch_related('items__product').order_by('-created_at')[:20]
    ]
    return JsonResponse({'ok': True, 'orders': orders})


@csrf_exempt
def telegram_webhook(request):
    if not bot_enabled():
        return JsonResponse({'ok': False, 'error': 'telegram bot disabled'}, status=503)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'method not allowed'}, status=405)

    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if secret:
        request_secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if request_secret != secret:
            return JsonResponse({'ok': False, 'error': 'invalid secret'}, status=403)

    try:
        update = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'invalid json'}, status=400)

    process_update(update)
    return JsonResponse({'ok': True})
