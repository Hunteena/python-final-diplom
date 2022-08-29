from django.contrib import admin
# from django.contrib.auth.models import Group
# from django.contrib.auth.admin import UserAdmin
# from .models import User
from .models import (
    Shop, Category, ProductInfo, Product, Parameter, ProductParameter,
    User, ConfirmEmailToken, Address, Order, OrderItem, Delivery
)


class OrderItemInline(admin.StackedInline):
    model = OrderItem
    extra = 0
    fields = [('product_info', 'quantity')]


# Register your models here.
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    fields = ['state', 'user', 'address']
    readonly_fields = ['user', 'address']
    list_display = ['id', 'user', 'state', 'dt']
    list_filter = ['user', 'state', 'dt']
    inlines = [OrderItemInline, ]


admin.site.register(Delivery)

# admin.site.register(User)
# admin.site.register(Shop)
# admin.site.register(Category)
# admin.site.register(ProductInfo)
# admin.site.register(Product)
# admin.site.register(Parameter)
# admin.site.register(ProductParameter)
# admin.site.register(Address)
# admin.site.register(ConfirmEmailToken)
