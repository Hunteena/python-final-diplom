from django.contrib import admin
# from django.contrib.auth.models import Group
# from django.contrib.auth.admin import UserAdmin
# from .models import User
from .models import (
    Shop, Category, ProductInfo, Product, Parameter, ProductParameter,
    User, ConfirmEmailToken, Address, Order, OrderItem, Delivery
)
from .signals import order_state_changed


# Register your models here.
class ProductParameterInline(admin.TabularInline):
    model = ProductParameter
    extra = 0
    fields = ('parameter', 'value')
    readonly_fields = ('parameter', 'value')
    can_delete = False


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    model = ProductInfo
    # extra = 0
    fields = (('id', 'external_id'), 'model', 'product', 'shop', 'quantity',
              ('price', 'price_rrc'))
    readonly_fields = ('id', 'model', 'external_id', 'product', 'shop',
                       'quantity', 'price', 'price_rrc')
    list_display = ('product', 'shop', 'quantity', 'price')
    list_filter = ('shop', )
    inlines = [ProductParameterInline, ]


class OrderItemInline(admin.StackedInline):
    model = OrderItem
    extra = 0
    fields = (('product_info', 'quantity'),)
    readonly_fields = ('product_info', 'quantity')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    fields = ('id', 'state', ('user', 'address'))
    readonly_fields = ('id', 'user', 'address')
    list_display = ('id', 'user', 'state', 'dt')
    list_filter = ('user', 'state', 'dt')
    inlines = [OrderItemInline, ]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        order_state_changed.send(sender=obj.__class__,
                                 user_id=obj.user.id,
                                 order_id=obj.id,
                                 state=obj.state)


class AddressInline(admin.StackedInline):
    model = Address
    fields = (('city', 'street'),
              ('house', 'structure'),
              ('building', 'apartment'))
    extra = 0


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    fields = (('type', 'is_active'), ('company', 'position'),
              ('first_name', 'patronymic', 'last_name'),
              ('email', 'phone'),
              ('date_joined', 'last_login'), 'is_superuser')
    list_display = ('__str__', 'type', 'is_active')
    list_filter = ('type', 'company')
    inlines = [AddressInline, ]


class DeliveryInline(admin.TabularInline):
    model = Delivery
    extra = 0


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'state')
    inlines = [DeliveryInline, ]


# class ProductInline(admin.StackedInline):
#     model = Product
#     fields = ('id', 'name')
#     extra = 0
#     can_delete = False
#
#
# @admin.register(Category)
# class CategoryAdmin(admin.ModelAdmin):
#     inlines = [ProductInline, ]

# admin.site.register(Shop)
admin.site.register(Category)
# admin.site.register(Product)
# admin.site.register(Parameter)
# admin.site.register(ProductParameter)
# admin.site.register(Address)
admin.site.register(ConfirmEmailToken)
