from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import User, Shop, Product, ProductParameter, \
    ProductInfo, OrderItem, Order, Category, Address


class AddressSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        MAX_ADDRESS_COUNT = 5
        address_count = Address.objects.filter(
            user_id=attrs['user']
        ).count()
        if address_count >= MAX_ADDRESS_COUNT:
            raise ValidationError(
                # TODO change error message?
                f'Максимальное количество адресов: {MAX_ADDRESS_COUNT}.'
            )
        return attrs

    class Meta:
        model = Address
        fields = ['id', 'user', 'city', 'street',
                  'house', 'structure', 'building', 'apartment']
        read_only_fields = ['id']
        extra_kwargs = {
            'user': {'write_only': True}
        }


class PartnerSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(default=False)
    type = serializers.CharField(default='shop', write_only=True)
    address = AddressSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'last_name', 'first_name', 'patronymic',
                  'company', 'position', 'phone', 'address',
                  'type', 'is_active']
        read_only_fields = ['id']


class UserSerializer(serializers.ModelSerializer):
    address = AddressSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'last_name', 'first_name', 'patronymic',
                  'company', 'position', 'phone', 'address']
        read_only_fields = ['id']


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ['id', 'name', 'state', ]
        read_only_fields = ['id']


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = ['name', 'category', ]


class ProductParameterSerializer(serializers.ModelSerializer):
    parameter = serializers.StringRelatedField()

    class Meta:
        model = ProductParameter
        fields = ['parameter', 'value', ]


class ProductInfoSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_parameters = ProductParameterSerializer(read_only=True, many=True)
    shop = ShopSerializer(read_only=True)

    class Meta:
        model = ProductInfo
        fields = ['id', 'model', 'product', 'shop', 'quantity', 'price',
                  'price_rrc', 'product_parameters', ]
        read_only_fields = ['id']


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'product_info', 'quantity', 'order', ]
        read_only_fields = ['id']
        extra_kwargs = {
            'order': {'write_only': True}
        }


class OrderItemCreateSerializer(OrderItemSerializer):
    product_info = ProductInfoSerializer(read_only=True)


class OrderSerializer(serializers.ModelSerializer):
    ordered_items = OrderItemCreateSerializer(read_only=True, many=True)

    total_sum = serializers.IntegerField()
    address = AddressSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'ordered_items', 'state', 'dt', 'total_sum',
                  'address'
                  # 'user'
                  ]
        read_only_fields = ['id']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name',)
        read_only_fields = ('id',)
