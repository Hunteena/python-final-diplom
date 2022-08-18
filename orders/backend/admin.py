from django.contrib import admin
# from django.contrib.auth.models import Group
# from django.contrib.auth.admin import UserAdmin
# from .models import User
from .models import (
    Shop, Category, ProductInfo, Product, Parameter, ProductParameter,
    User, ConfirmEmailToken, Address
)

# Register your models here.
admin.site.register(User)
admin.site.register(Shop)
admin.site.register(Category)
admin.site.register(ProductInfo)
admin.site.register(Product)
admin.site.register(Parameter)
admin.site.register(ProductParameter)
admin.site.register(Address)
admin.site.register(ConfirmEmailToken)
