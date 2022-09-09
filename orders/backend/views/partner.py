import datetime
from distutils.util import strtobool

import requests as rqs
import yaml
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Sum, F
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    Shop, Category, ProductInfo, Product, Parameter, ProductParameter,
    Order, Delivery
)
from ..serializers import PartnerSerializer, ShopSerializer, \
    OrderSerializer, PartnerOrderSerializer, DeliverySerializer
from ..signals import new_user_registered, price_list_updated


class RegisterPartner(APIView):
    """
    Для регистрации поставщиков
    """

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):

        # проверяем обязательные аргументы
        if not {'email', 'password', 'company'}.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
            )

        # проверяем пароль на сложность
        try:
            validate_password(request.data['password'])
        except Exception as password_error:
            return JsonResponse(
                {'Status': False,
                 'Errors': {'password': list(password_error)}},
                status=400
            )
        else:
            # проверяем данные для уникальности имени пользователя
            partner_serializer = PartnerSerializer(data=request.data)
            if partner_serializer.is_valid():
                # сохраняем пользователя
                user = partner_serializer.save()
                user.set_password(request.data['password'])
                user.save()
                new_user_registered.send(sender=self.__class__,
                                         user_id=user.id)
                return JsonResponse({'Status': True})
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': partner_serializer.errors},
                    status=400
                )


class PartnerUpdate(APIView):
    """
    Класс для получения информации для обновления прайс-листа
    """

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'},
                status=403
            )

        if request.user.type != 'shop':
            return JsonResponse(
                {'Status': False, 'Error': 'Только для магазинов'},
                status=403
            )

        data = {'file': None, 'url': None,
                'update_dt': datetime.date.today(), 'is_uptodate': False}
        file = request.FILES.get('file')
        url = request.data.get('url')
        if file:
            data['file'] = file
        elif url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)},
                                    status=400)
            data['url'] = url
        else:
            return JsonResponse({'Status': False,
                                 'Error': 'Необходим либо файл, либо ссылка.'})

        shop, _ = Shop.objects.get_or_create(user_id=request.user.id)
        data['name'] = f"- Актуализируйте прайс-лист -"
        shop_serializer = ShopSerializer(shop, data=data,
                                         partial=True)
        if shop_serializer.is_valid():
            shop_serializer.save()
            price_list_updated.send(sender=self.__class__,
                                    user=request.user,
                                    shop_name=shop_serializer.data['name'])

            return JsonResponse({'Status': True})
        else:
            return JsonResponse(
                {'Status': False, 'Errors': shop_serializer.errors},
                status=400
            )


class UpdatePrices(APIView):
    """
    Класс для обновления прайса от поставщика
    """

    def post(self, request, *args, **kwargs):
        # if not request.user.is_authenticated:
        #     return JsonResponse(
        #         {'Status': False, 'Error': 'Log in required'},
        #         status=403
        #     )
        #
        # if request.user.type != 'shop':
        #     return JsonResponse(
        #         {'Status': False, 'Error': 'Только для магазинов'},
        #         status=403
        #     )

        user_id = request.data.get('user_id')

        file = request.data.get('file')
        url = request.data.get('url')
        if file:
            stream = ...
        elif url:
            stream = rqs.get(url).content
        else:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
            )

        data = yaml.safe_load(stream)

        shop, _ = Shop.objects.get_or_create(
            name=data['shop'], user_id=user_id
        )
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

        return JsonResponse({'Status': True})


class PartnerState(APIView):
    """
    Класс для работы со статусом поставщика
    """

    # получить текущий статус
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )

        if request.user.type != 'shop':
            return JsonResponse(
                {'Status': False, 'Error': 'Только для магазинов'}, status=403
            )

        shop = request.user.shop
        serializer = ShopSerializer(shop)
        return Response(serializer.data['state'])

    # изменить текущий статус
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )

        if request.user.type != 'shop':
            return JsonResponse(
                {'Status': False, 'Error': 'Только для магазинов'}, status=403
            )

        state = request.data.get('state')
        if not state:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
            )

        try:
            Shop.objects.filter(
                user_id=request.user.id
            ).update(
                state=strtobool(state)
            )
            return JsonResponse({'Status': True})
        except ValueError as error:
            return JsonResponse(
                {'Status': False, 'Errors': str(error)}, status=400
            )


class PartnerOrders(APIView):
    """
    Класс для получения заказов поставщиками
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )

        if request.user.type != 'shop':
            return JsonResponse(
                {'Status': False, 'Error': 'Только для магазинов'}, status=403
            )

        order = Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id
        ).exclude(
            state='basket'
        ).prefetch_related(
            'ordered_items__product_info__shop',
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter'
        ).select_related(
            'user'
        ).annotate(
            total_sum=Sum(F('ordered_items__quantity') *
                          F('ordered_items__product_info__price'))
        ).distinct()

        serializer = PartnerOrderSerializer(order, partner_id=request.user.id,
                                            many=True)
        return Response(serializer.data)


class DeliveryView(APIView):
    """
    Класс для стоимости доставки
    """

    def get(self, request, *args, **kwargs):
        shop = request.GET.get('shop')
        if shop:
            delivery = Delivery.objects.filter(shop=shop).order_by('-min_sum')
        else:
            delivery = Delivery.objects.order_by('shop', '-min_sum')
        serializer = DeliverySerializer(delivery, many=True)
        return Response(serializer.data)

    # def post(self, request, *args, **kwargs):
    #     if not request.user.is_authenticated:
    #         return JsonResponse(
    #             {'Status': False, 'Error': 'Log in required'}, status=403
    #         )
    #
    #     if request.user.type != 'shop':
    #         return JsonResponse(
    #             {'Status': False, 'Error': 'Только для магазинов'}, status=403
    #         )
    #
    #     if not {'min_sum', 'street'}.issubset(request.data):
    #         return JsonResponse(
    #             {'Status': False,
    #              'Errors': 'Не указаны все необходимые аргументы'},
    #             status=400
    #         )
