from distutils.util import strtobool

import requests as rqs
import yaml
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Sum, F, Q
from django.http import JsonResponse
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Shop, Category, ProductInfo, Product, Parameter, ProductParameter,
    ConfirmEmailToken, Order, OrderItem, Address
)
from .serializers import PartnerSerializer, UserSerializer, ShopSerializer, \
    OrderSerializer, CategorySerializer, \
    ProductInfoSerializer, OrderItemSerializer, AddressSerializer
from .signals import new_order, new_user_registered


class RegisterPartner(APIView):
    """
    Для регистрации поставщиков
    """

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):

        # проверяем обязательные аргументы
        if not {'email', 'password', 'company'}.issubset(request.data):
            return JsonResponse({
                'Status': False,
                'Errors': 'Не указаны все необходимые аргументы'
            })

        # проверяем пароль на сложность
        try:
            validate_password(request.data['password'])
        except Exception as password_error:
            return JsonResponse({'Status': False,
                                 'Errors': {'password': list(password_error)}})
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
                    {'Status': False, 'Errors': partner_serializer.errors})


class PartnerUpdate(APIView):
    """
    Класс для обновления прайса от поставщика
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

        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)})
            else:
                stream = rqs.get(url).content

                data = yaml.safe_load(stream)

                shop, _ = Shop.objects.get_or_create(
                    name=data['shop'], user_id=request.user.id
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

        return JsonResponse(
            {'Status': False,
             'Errors': 'Не указаны все необходимые аргументы'}
        )


class RegisterAccount(APIView):
    """
    Для регистрации покупателей
    """

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):

        # проверяем обязательные аргументы
        required_fields = {'first_name', 'last_name',
                           'email', 'password',
                           'company', 'position'}
        if not required_fields.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        # проверяем пароль на сложность
        try:
            validate_password(request.data['password'])
        except Exception as password_error:
            return JsonResponse(
                {'Status': False,
                 'Errors': {'password': list(password_error)}}
            )
        else:
            # проверяем данные для уникальности имени пользователя
            user_serializer = UserSerializer(data=request.data)
            if user_serializer.is_valid():
                # сохраняем пользователя
                user = user_serializer.save()
                user.set_password(request.data['password'])
                user.save()
                new_user_registered.send(sender=self.__class__,
                                         user_id=user.id)
                return JsonResponse({'Status': True})
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': user_serializer.errors}
                )


class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):

        # проверяем обязательные аргументы
        if not {'email', 'token'}.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        token = ConfirmEmailToken.objects.filter(
            user__email=request.data['email'],
            key=request.data['token']
        ).first()
        if token:
            token.user.is_active = True
            token.user.save()
            token.delete()
            return JsonResponse({'Status': True})
        else:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Неправильно указан токен или email'}
            )


class LoginAccount(APIView):
    """
    Класс для авторизации пользователей
    """

    # Авторизация методом POST
    def post(self, request, *args, **kwargs):

        if not {'email', 'password'}.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        user = authenticate(request, username=request.data['email'],
                            password=request.data['password'])

        if user is not None:
            if user.is_active:
                token, _ = Token.objects.get_or_create(user=user)

                return JsonResponse({'Status': True, 'Token': token.key})

        return JsonResponse(
            {'Status': False, 'Errors': 'Не удалось авторизовать'})


class AccountDetails(APIView):
    """
    Класс для работы данными пользователя
    """

    # получить данные
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=403)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # Редактирование методом POST
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=403)

        if 'password' in request.data:
            errors = {}
            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                return JsonResponse(
                    {'Status': False,
                     'Errors': {'password': list(password_error)}}
                )
            else:
                request.user.set_password(request.data['password'])

        # проверяем остальные данные
        user_serializer = UserSerializer(request.user, data=request.data,
                                         partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True})
        else:
            return JsonResponse(
                {'Status': False, 'Errors': user_serializer.errors})


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
        return Response(serializer.data)

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
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        try:
            Shop.objects.filter(
                user_id=request.user.id
            ).update(
                state=strtobool(state)
            )
            return JsonResponse({'Status': True})
        except ValueError as error:
            return JsonResponse({'Status': False, 'Errors': str(error)})


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
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter'
        ).select_related(
            'user'
        ).annotate(
            total_sum=Sum(F('ordered_items__quantity') *
                          F('ordered_items__product_info__price'))
        ).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


class AddressView(APIView):
    """
    Класс для работы с адресами покупателей
    """

    # получить мои контакты
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=403)
        address = Address.objects.filter(user_id=request.user.id)
        serializer = AddressSerializer(address, many=True)
        return Response(serializer.data)

    # добавить новый контакт
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=403)

        if not {'city', 'street'}.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        # request.data._mutable = True
        request.data.update({'user': request.user.id})
        serializer = AddressSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return JsonResponse({'Status': True})
        else:
            return JsonResponse({'Status': False, 'Errors': serializer.errors})

    # удалить контакт
    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=403)

        items_string = request.data.get('items')
        if not items_string:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        items_list = items_string.split(',')
        query = Q()
        objects_deleted = False
        for address_id in items_list:
            if address_id.isdigit():
                query = query | Q(user_id=request.user.id, id=address_id)
                objects_deleted = True

        if objects_deleted:
            deleted_count = Address.objects.filter(query).delete()[0]
            return JsonResponse(
                {'Status': True, 'Удалено объектов': deleted_count})
        # TODO response 'не удалось удалить объекты'?

    # редактировать контакт
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=403)

        if 'id' not in request.data:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        if request.data['id'].isdigit():
            address = Address.objects.filter(
                id=request.data['id'], user_id=request.user.id
            ).first()
            if address:
                serializer = AddressSerializer(address, data=request.data,
                                               partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse(
                        {'Status': False, 'Errors': serializer.errors}
                    )
        # TODO response 'нет такого адреса'?


class CategoryView(ListAPIView):
    """
    Класс для просмотра категорий
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ShopView(ListAPIView):
    """
    Класс для просмотра списка магазинов
    """
    queryset = Shop.objects.filter(state=True)
    serializer_class = ShopSerializer


class ProductInfoView(APIView):
    """
    Класс для поиска товаров
    """

    def get(self, request, *args, **kwargs):

        query = Q(shop__state=True)
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')

        if shop_id:
            query = query & Q(shop_id=shop_id)

        if category_id:
            query = query & Q(product__category_id=category_id)

        # фильтруем и отбрасываем дубликаты
        queryset = ProductInfo.objects.filter(
            query
        ).select_related(
            'shop', 'product__category'
        ).prefetch_related(
            'product_parameters__parameter'
        ).distinct()

        serializer = ProductInfoSerializer(queryset, many=True)

        return Response(serializer.data)


class BasketView(APIView):
    """
    Класс для работы с корзиной пользователя
    """

    # получить корзину
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )

        basket = Order.objects.filter(
            user_id=request.user.id, state='basket'
        ).prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter'
        ).annotate(
            total_sum=Sum(F('ordered_items__quantity') *
                          F('ordered_items__product_info__price'))
        ).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    # добавить позиции в корзину
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )

        items_list = request.data.get('items')
        if not items_list:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        basket, _ = Order.objects.get_or_create(
            user_id=request.user.id, state='basket'
        )
        objects_created = 0
        for order_item in items_list:
            order_item.update({'order': basket.id})
            serializer = OrderItemSerializer(data=order_item)
            if serializer.is_valid():
                try:
                    serializer.save()
                except IntegrityError as error:
                    return JsonResponse(
                        {'Status': False, 'Errors': str(error)}
                    )
                else:
                    objects_created += 1
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': serializer.errors}
                )

        return JsonResponse(
            {'Status': True, 'Создано объектов': objects_created}
        )

    # удалить товары из корзины
    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'},
                                status=403)

        items_list = request.data.get('items')
        if not items_list:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        basket, _ = Order.objects.get_or_create(
            user_id=request.user.id, state='basket'
        )
        query = Q()
        have_objects_to_delete = False
        for order_item_id in items_list:
            if type(order_item_id) == int:
                query = query | Q(order_id=basket.id, id=order_item_id)
                have_objects_to_delete = True
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': 'Неверный формат запроса'}
                )

        if have_objects_to_delete:
            deleted_count = OrderItem.objects.filter(query).delete()[0]
            return JsonResponse(
                {'Status': True, 'Удалено объектов': deleted_count})

    # изменить количество позиции в корзине
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )

        items_list = request.data.get('items')
        if not items_list:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        basket, _ = Order.objects.get_or_create(
            user_id=request.user.id, state='basket'
        )
        objects_updated = 0
        for order_item in items_list:
            item_id, qty = order_item.get('id'), order_item.get('quantity')

            if type(item_id) == int and type(qty) == int:
                objects_updated += OrderItem.objects.filter(
                    order_id=basket.id, id=item_id
                ).update(
                    quantity=qty
                )

        return JsonResponse(
            {'Status': True, 'Обновлено объектов': objects_updated}
        )


class OrderView(APIView):
    """
    Класс для получения и размешения заказов пользователями
    """

    # получить мои заказы
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )
        order = Order.objects.filter(
            user_id=request.user.id
        ).exclude(
            state='basket'
        ).prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter'
        ).select_related(
            'address'
        ).annotate(
            total_sum=Sum(F('ordered_items__quantity')
                          * F('ordered_items__product_info__price'))
        ).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    # разместить заказ из корзины
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'Status': False, 'Error': 'Log in required'}, status=403
            )

        if not {'id', 'address'}.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'}
            )

        if type(request.data['id']) == int:
            try:
                is_updated = Order.objects.filter(
                    user_id=request.user.id, id=request.data['id']
                ).update(
                    address_id=request.data['address'],
                    state='new'
                )
            except IntegrityError as error:
                print(error)
                return JsonResponse(
                    {'Status': False,
                     'Errors': 'Неправильно указаны аргументы'}
                )
            else:
                if is_updated:
                    new_order.send(sender=self.__class__,
                                   user_id=request.user.id)
                    return JsonResponse({'Status': True})

