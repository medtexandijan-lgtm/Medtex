from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from .models import User, Category, Product, Client, Sale, SaleItem, WarehouseTransaction
from .forms import (
    LoginForm, UserCreationForm, UserChangeForm,
    CategoryForm, ProductForm, ClientForm, SaleForm,
    WarehouseTransactionForm
)


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
            else:
                messages.error(request, 'Foydalanuvchi nomi yoki parol notoʻgʻri')
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    context = {}
    user_role = request.user.role
    
    if user_role == 'director':
        context['total_products'] = Product.objects.count()
        context['total_clients'] = Client.objects.count()
        context['total_sales'] = Sale.objects.count()
        context['total_revenue'] = Sale.objects.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        context['recent_sales'] = Sale.objects.select_related('client', 'seller').order_by('-created_at')[:10]
        context['top_products'] = Product.objects.order_by('-stock')[:5]
    elif user_role == 'seller':
        context['my_sales'] = Sale.objects.filter(seller=request.user).count()
        context['today_sales'] = Sale.objects.filter(seller=request.user, created_at__date='today').count()
        context['my_revenue'] = Sale.objects.filter(seller=request.user, status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        context['recent_sales'] = Sale.objects.filter(seller=request.user).select_related('client').order_by('-created_at')[:10]
    elif user_role == 'warehouse':
        context['total_products'] = Product.objects.count()
        context['low_stock'] = Product.objects.filter(stock__lt=10).count()
        context['total_stock'] = Product.objects.aggregate(Sum('stock'))['stock__sum'] or 0
        context['recent_transactions'] = WarehouseTransaction.objects.select_related('product', 'created_by').order_by('-created_at')[:10]
    
    return render(request, 'dashboard.html', context)


@login_required
def users_list(request):
    if request.user.role != 'director':
        messages.error(request, 'Sizga bu sahifaga kirish ruxsati yoʻq')
        return redirect('dashboard')
    
    users = User.objects.all()
    return render(request, 'users.html', {'users': users})


@login_required
def user_create(request):
    if request.user.role != 'director':
        messages.error(request, 'Sizga bu sahifaga kirish ruxsati yoʻq')
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
        messages.error(request, 'Sizga bu sahifaga kirish ruxsati yoʻq')
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
        messages.error(request, 'Sizga bu sahifaga kirish ruxsati yoʻq')
        return redirect('dashboard')
    
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'Oʻzingizni oʻchira olmaysiz')
    else:
        user.delete()
        messages.success(request, 'Foydalanuvchi oʻchirildi')
    return redirect('users')


@login_required
def categories_list(request):
    categories = Category.objects.annotate(product_count=Count('products'))
    return render(request, 'categories.html', {'categories': categories})


@login_required
def category_create(request):
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
    category = get_object_or_404(Category, pk=pk)
    category.delete()
    messages.success(request, 'Kategoriya oʻchirildi')
    return redirect('categories')


@login_required
def products_list(request):
    search = request.GET.get('search', '')
    category_id = request.GET.get('category', '')
    
    products = Product.objects.select_related('category')
    
    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if category_id:
        products = products.filter(category_id=category_id)
    
    categories = Category.objects.all()
    return render(request, 'products.html', {'products': products, 'categories': categories})


@login_required
def product_create(request):
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
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.success(request, 'Mahsulot oʻchirildi')
    return redirect('products')


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('category'), pk=pk)
    transactions = product.transactions.order_by('-created_at')[:10]
    return render(request, 'product_detail.html', {'product': product, 'transactions': transactions})


@login_required
def clients_list(request):
    search = request.GET.get('search', '')
    clients = Client.objects.all()
    if search:
        clients = clients.filter(Q(name__icontains=search) | Q(phone__icontains=search) | Q(company__icontains=search))
    return render(request, 'clients.html', {'clients': clients})


@login_required
def client_create(request):
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
    client = get_object_or_404(Client, pk=pk)
    client.delete()
    messages.success(request, 'Mijoz oʻchirildi')
    return redirect('clients')


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    sales = client.sales.select_related('seller').order_by('-created_at')[:20]
    total_spent = client.sales.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    return render(request, 'client_detail.html', {'client': client, 'sales': sales, 'total_spent': total_spent})


@login_required
def sales_list(request):
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    sales = Sale.objects.select_related('client', 'seller')
    
    if request.user.role == 'seller':
        sales = sales.filter(seller=request.user)
    
    if status:
        sales = sales.filter(status=status)
    if date_from:
        sales = sales.filter(created_at__date__gte=date_from)
    if date_to:
        sales = sales.filter(created_at__date__lte=date_to)
    
    sales = sales.order_by('-created_at')
    return render(request, 'sales.html', {'sales': sales})


@login_required
def sale_create(request):
    if request.method == 'POST':
        client_id = request.POST.get('client')
        notes = request.POST.get('notes')
        
        client = get_object_or_404(Client, pk=client_id)
        sale = Sale.objects.create(
            client=client,
            seller=request.user,
            total_amount=0,
            notes=notes
        )
        
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')
        
        total = 0
        for pid, qty in zip(product_ids, quantities):
            if pid and qty:
                product = get_object_or_404(Product, pk=pid)
                qty = int(qty)
                if product.stock >= qty:
                    unit_price = product.price
                    item_total = unit_price * qty
                    SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=qty,
                        unit_price=unit_price,
                        total_price=item_total
                    )
                    total += item_total
                    product.stock -= qty
                    product.save()
                else:
                    messages.error(request, f'{product.name} uchun yetarli mahsulot yoʻq')
        
        sale.total_amount = total
        sale.status = 'completed'
        sale.save()
        
        messages.success(request, f'Sotuv #{sale.id} muvaffaqiyatli yaratildi')
        return redirect('sales')
    
    clients = Client.objects.all()
    products = Product.objects.filter(stock__gt=0)
    return render(request, 'sale_form.html', {'clients': clients, 'products': products, 'action': 'create'})


@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale.objects.select_related('client', 'seller'), pk=pk)
    items = sale.items.select_related('product')
    return render(request, 'sale_detail.html', {'sale': sale, 'items': items})


@login_required
def sale_update_status(request, pk):
    if request.method == 'POST':
        sale = get_object_or_404(Sale, pk=pk)
        new_status = request.POST.get('status')
        
        if new_status == 'cancelled' and sale.status == 'completed':
            for item in sale.items.all():
                product = item.product
                product.stock += item.quantity
                product.save()
        
        sale.status = new_status
        sale.save()
        messages.success(request, 'Sotuv holati yangilandi')
        return redirect('sale_detail', pk=pk)


@login_required
def warehouse(request):
    search = request.GET.get('search', '')
    products = Product.objects.select_related('category')
    
    if search:
        products = products.filter(name__icontains=search)
    
    return render(request, 'warehouse.html', {'products': products})


@login_required
def warehouse_transaction(request):
    if request.method == 'POST':
        form = WarehouseTransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.created_by = request.user
            transaction.save()
            
            product = transaction.product
            if transaction.transaction_type == 'in':
                product.stock += transaction.quantity
            else:
                product.stock -= transaction.quantity
            product.save()
            
            messages.success(request, 'Ombor operatsiyasi muvaffaqiyatli amalga oshirildi')
            return redirect('warehouse')
    else:
        form = WarehouseTransactionForm()
    
    products = Product.objects.filter(stock__gt=0)
    return render(request, 'transaction_form.html', {'form': form, 'products': products})


@login_required
def transactions_history(request):
    transactions = WarehouseTransaction.objects.select_related('product', 'created_by').order_by('-created_at')
    return render(request, 'transactions.html', {'transactions': transactions})


@login_required
def reports(request):
    if request.user.role != 'director':
        messages.error(request, 'Sizga bu sahifaga kirish ruxsati yoʻq')
        return redirect('dashboard')
    
    total_revenue = Sale.objects.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_sales = Sale.objects.filter(status='completed').count()
    total_clients = Client.objects.count()
    total_products = Product.objects.count()
    
    sales_by_month = Sale.objects.filter(status='completed').extra(
        select={'month': "strftime('%%Y-%%m', created_at)"}
    ).values('month').annotate(total=Sum('total_amount')).order_by('month')
    
    top_sellers = User.objects.filter(role='seller').annotate(
        sales_count=Count('sales'),
        total_sales=Sum('sales__total_amount', filter=models.Q(sales__status='completed'))
    ).order_by('-total_sales')[:5]
    
    top_products = SaleItem.objects.values('product__name').annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum('total_price')
    ).order_by('-total_revenue')[:10]
    
    context = {
        'total_revenue': total_revenue,
        'total_sales': total_sales,
        'total_clients': total_clients,
        'total_products': total_products,
        'sales_by_month': sales_by_month,
        'top_sellers': top_sellers,
        'top_products': top_products,
    }
    return render(request, 'reports.html', context)


@login_required
def get_product_price(request):
    product_id = request.GET.get('product_id')
    try:
        product = Product.objects.get(pk=product_id)
        return JsonResponse({
            'price': str(product.price),
            'stock': product.stock,
            'unit': product.unit
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Mahsulot topilmadi'}, status=404)


@login_required
def product_select(request):
    products = Product.objects.filter(stock__gt=0).values('id', 'name', 'price', 'stock', 'unit')
    return JsonResponse(list(products), safe=False)