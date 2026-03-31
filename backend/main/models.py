from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = [
        ('director', 'Direktor'),
        ('seller', 'Sotuvchi'),
        ('warehouse', 'Omborchi'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='seller')
    phone = models.CharField(max_length=20, blank=True)
    
    class Meta:
        verbose_name = 'Foydalanuvchi'
        verbose_name_plural = 'Foydalanuvchilar'


class Category(models.Model):
    name = models.CharField(max_length=200, verbose_name='Kategoriya nomi')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Kategoriya'
        verbose_name_plural = 'Kategoriyalar'


class Product(models.Model):
    name = models.CharField(max_length=300, verbose_name='Mahsulot nomi')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products', verbose_name='Kategoriya')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Narxi (soʻm)')
    stock = models.PositiveIntegerField(default=0, verbose_name='Ombordagi soni')
    unit = models.CharField(max_length=50, default='dona', verbose_name='Oʻlchov birligi')
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name='Rasm')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Mahsulot'
        verbose_name_plural = 'Mahsulotlar'


class Client(models.Model):
    name = models.CharField(max_length=200, verbose_name='Mijoz nomi')
    phone = models.CharField(max_length=20, verbose_name='Telefon')
    email = models.EmailField(blank=True, verbose_name='Email')
    address = models.TextField(blank=True, verbose_name='Manzil')
    company = models.CharField(max_length=200, blank=True, verbose_name='Kompaniya')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Mijoz'
        verbose_name_plural = 'Mijozlar'


class SellerShift(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shifts', verbose_name='Sotuvchi')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Boshlangan vaqti')
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name='Yopilgan vaqti')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.seller.username} - {self.started_at:%d.%m.%Y %H:%M}"

    @property
    def is_open(self):
        return self.ended_at is None

    class Meta:
        verbose_name = 'Sotuvchi smenasi'
        verbose_name_plural = 'Sotuvchi smenalari'
        ordering = ['-started_at']


class Sale(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('completed', 'Tugallangan'),
        ('cancelled', 'Bekor qilingan'),
        ('returned', 'Qaytarilgan'),
    ]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='sales', verbose_name='Mijoz', null=True, blank=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sales', verbose_name='Sotuvchi')
    shift = models.ForeignKey(
        SellerShift,
        on_delete=models.SET_NULL,
        related_name='sales',
        verbose_name='Smena',
        null=True,
        blank=True,
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Jami summa')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Holat')
    notes = models.TextField(blank=True, verbose_name='Izoh')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Sotuv #{self.id}"
    
    class Meta:
        verbose_name = 'Sotuv'
        verbose_name_plural = 'Sotuvlar'


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items', verbose_name='Sotuv')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sale_items', verbose_name='Mahsulot')
    quantity = models.PositiveIntegerField(verbose_name='Soni')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Birlik narxi')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Jami narx')
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    class Meta:
        verbose_name = 'Sotuv elementi'
        verbose_name_plural = 'Sotuv elementlari'


class WarehouseTransaction(models.Model):
    TYPE_CHOICES = [
        ('in', 'Kirim'),
        ('out', 'Chiqim'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='transactions', verbose_name='Mahsulot')
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name='Amal turi')
    quantity = models.PositiveIntegerField(verbose_name='Soni')
    notes = models.TextField(blank=True, verbose_name='Izoh')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Kim tomonidan')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.product.name}"
    
    class Meta:
        verbose_name = 'Ombor operatsiyasi'
        verbose_name_plural = 'Ombor operatsiyalari'


class TelegramProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='telegram_profile',
        null=True,
        blank=True,
    )
    chat_id = models.BigIntegerField(unique=True, verbose_name='Chat ID')
    chat_username = models.CharField(max_length=255, blank=True, verbose_name='Telegram username')
    first_name = models.CharField(max_length=255, blank=True, verbose_name='Ism')
    last_name = models.CharField(max_length=255, blank=True, verbose_name='Familiya')
    is_active = models.BooleanField(default=True, verbose_name='Faol')
    linked_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} -> {self.chat_id}"

    class Meta:
        verbose_name = 'Telegram profili'
        verbose_name_plural = 'Telegram profillari'


class TelegramLinkCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='telegram_link_codes')
    code = models.CharField(max_length=12, unique=True, verbose_name='Link kodi')
    expires_at = models.DateTimeField(verbose_name='Amal qilish muddati')
    is_used = models.BooleanField(default=False, verbose_name='Ishlatilgan')
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.code}"

    class Meta:
        verbose_name = 'Telegram link kodi'
        verbose_name_plural = 'Telegram link kodlari'


class TelegramOrder(models.Model):
    STATUS_CHOICES = [
        ('new', 'Yangi'),
        ('confirmed', 'Tasdiqlangan'),
        ('cancelled', 'Bekor qilingan'),
        ('completed', 'Yakunlangan'),
    ]

    profile = models.ForeignKey(TelegramProfile, on_delete=models.CASCADE, related_name='orders')
    full_name = models.CharField(max_length=255, verbose_name='Buyurtmachi ismi')
    phone = models.CharField(max_length=30, verbose_name='Telefon')
    comment = models.TextField(blank=True, verbose_name='Izoh')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name='Holat')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Jami summa')
    sale = models.OneToOneField(
        'Sale',
        on_delete=models.SET_NULL,
        related_name='telegram_order',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Telegram order #{self.id}"

    class Meta:
        verbose_name = 'Telegram buyurtma'
        verbose_name_plural = 'Telegram buyurtmalar'


class TelegramOrderItem(models.Model):
    order = models.ForeignKey(TelegramOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='telegram_order_items')
    quantity = models.PositiveIntegerField(verbose_name='Soni')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Birlik narxi')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Jami narx')

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    class Meta:
        verbose_name = 'Telegram buyurtma elementi'
        verbose_name_plural = 'Telegram buyurtma elementlari'
