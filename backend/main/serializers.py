from rest_framework import serializers

from .models import Category, Client, Product, Sale, SaleItem, SellerShift, TelegramOrder, TelegramOrderItem, User


class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'role']

    def get_full_name(self, obj):
        return obj.get_full_name().strip() or obj.username


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source='category',
        queryset=Category.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'category',
            'category_id',
            'description',
            'price',
            'stock',
            'unit',
            'created_at',
            'updated_at',
        ]


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name', 'phone', 'email', 'address', 'company', 'created_at', 'updated_at']


class SaleItemReadSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = SaleItem
        fields = ['id', 'product', 'quantity', 'unit_price', 'total_price']


class SaleSerializer(serializers.ModelSerializer):
    client = ClientSerializer(read_only=True)
    seller = UserSummarySerializer(read_only=True)
    shift_id = serializers.IntegerField(source='shift.id', read_only=True)
    items = SaleItemReadSerializer(read_only=True, many=True)

    class Meta:
        model = Sale
        fields = [
            'id',
            'client',
            'seller',
            'shift_id',
            'total_amount',
            'status',
            'notes',
            'created_at',
            'updated_at',
            'items',
        ]


class SaleItemWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class SaleCreateSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = SaleItemWriteSerializer(many=True)


class SellerShiftSerializer(serializers.ModelSerializer):
    seller = UserSummarySerializer(read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = SellerShift
        fields = ['id', 'seller', 'started_at', 'ended_at', 'is_open']


class SellerShiftReportSerializer(serializers.Serializer):
    shift = SellerShiftSerializer()
    total_sales = serializers.IntegerField()
    total_quantity = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    items = SaleItemReadSerializer(many=True)


class TelegramOrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = TelegramOrderItem
        fields = ['id', 'product', 'quantity', 'unit_price', 'total_price']


class CourierOrderSerializer(serializers.ModelSerializer):
    courier = UserSummarySerializer(read_only=True)
    items = TelegramOrderItemSerializer(read_only=True, many=True)
    sale_id = serializers.IntegerField(source='sale.id', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TelegramOrder
        fields = [
            'id',
            'full_name',
            'phone',
            'comment',
            'status',
            'status_display',
            'total_amount',
            'sale_id',
            'courier',
            'created_at',
            'updated_at',
            'items',
        ]


class CourierStatsSerializer(serializers.Serializer):
    available_orders = serializers.IntegerField()
    active_orders = serializers.IntegerField()
    completed_orders = serializers.IntegerField()
