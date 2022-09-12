import requests as rqs
import yaml
from django.contrib import admin
# from django.contrib.auth.models import Group
# from django.contrib.auth.admin import UserAdmin
# from .models import User
from django.contrib.admin import helpers
from django.template.response import TemplateResponse
from django.urls import path

from .models import (
    Shop, Category, ProductInfo, ProductParameter,
    User, ConfirmEmailToken, Address, Order, OrderItem, Delivery, Product,
    Parameter, STATE_CHOICES
)
from .tasks import send_email_task


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
    list_filter = ('shop',)
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

        # отправляем письмо пользователю при изменении статуса заказа
        rus_state = ''
        for state_tuple in STATE_CHOICES:
            if state_tuple[0] == obj.state:
                rus_state = state_tuple[1]
                break

        title = f"Обновление статуса заказа {obj.id}"
        message = f'Заказ {obj.id} получил статус {rus_state}.'
        addressee_list = [obj.user.email]
        send_email_task.delay(title, message, addressee_list)


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


@admin.action(description='Актуализировать прайс-листы выбранных магазинов')
def make_uptodate(modeladmin, request, queryset):
    """
    Action which updates prices for the selected shops.

    This action first displays a confirmation page.
    """
    context = {
        **modeladmin.admin_site.each_context(request),
        'title': 'Требуется подтверждение',
        # 'objects_name': str(objects_name),
        'selected': [*queryset],
        # 'model_count': dict(model_count).items(),
        'queryset': queryset,
        # 'perms_lacking': perms_needed,
        # 'protected': protected,
        'opts': modeladmin.model._meta,
        'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
        # 'media': modeladmin.media,
        'update_href': 'update/?ids=' + ','.join([str(shop.id)
                                                  for shop in queryset])
    }

    request.current_app = modeladmin.admin_site.name

    # Display the confirmation page
    return TemplateResponse(
        request,
        "admin/backend/shop/update_selected_confirmation.html",
        context
    )


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    # TODO show right link to file or just filename
    fields = ('state', ('name', 'id',), ('user',), ('url', 'file'),
              'update_dt', 'is_uptodate')
    readonly_fields = ('id', 'url', 'file')
    list_display = ('name', 'user', 'state', 'is_uptodate')
    inlines = [DeliveryInline, ]
    actions = [make_uptodate, ]

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('update/', self.make_uptodate_view),
        ]
        return my_urls + urls

    def make_uptodate_view(self, request):
        context = dict(
            # Include common variables for rendering the admin template.
            self.admin_site.each_context(request),
            opts=self.model._meta,
            action_checkbox_name=helpers.ACTION_CHECKBOX_NAME,
            title='Результат операции'
        )
        ids = request.GET.get('ids')
        updated, not_updated, already_updated = [], dict(), []

        for shop_id in ids.split(','):
            shop = Shop.objects.get(id=shop_id)

            if shop.is_uptodate:
                already_updated.append(shop.name)
                continue

            if shop.file:
                stream = shop.file
            elif shop.url:
                try:
                    result = rqs.get(shop.url)
                except rqs.exceptions.ConnectionError:
                    not_updated[shop.name] = 'Нет соединения'
                    continue
                else:
                    if result.ok:
                        stream = result.content
                    else:
                        not_updated[shop.name] = 'Файл не найден'
                        continue
            else:
                not_updated[shop.name] = 'Нет файла для актуализации'
                continue

            data = yaml.safe_load(stream)

            # TODO clear shop categories?
            for category in data['categories']:
                category_object, _ = Category.objects.get_or_create(
                    id=category['id'], name=category['name']
                )
                category_object.shops.add(shop.id)
                category_object.save()
            ProductInfo.objects.filter(shop_id=shop.id).delete()
            for item in data['goods']:
                product, _ = Product.objects.get_or_create(
                    name=item['name'], category_id=item['category']
                )

                product_info = ProductInfo.objects.create(
                    product_id=product.id,
                    external_id=item['id'],
                    model=item['model'],
                    price=item['price'],
                    price_rrc=item['price_rrc'],
                    quantity=item['quantity'],
                    shop_id=shop.id
                )
                for name, value in item['parameters'].items():
                    parameter_object, _ = Parameter.objects.get_or_create(
                        name=name
                    )
                    ProductParameter.objects.create(
                        product_info_id=product_info.id,
                        parameter_id=parameter_object.id,
                        value=value
                    )

            shop.name = data['shop']
            shop.is_uptodate = True
            shop.save()
            updated.append(shop)

        context.update(updated=updated,
                       not_updated=not_updated,
                       already_updated=already_updated)
        return TemplateResponse(request,
                                "admin/backend/shop/update_result.html",
                                context)


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
