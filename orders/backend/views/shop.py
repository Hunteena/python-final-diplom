from django.db import IntegrityError
from django.db.models import Sum, F, Q
from django.http import JsonResponse
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    Shop, ProductInfo, Order, OrderItem, Category, Delivery
)
from ..serializers import ShopSerializer, \
    OrderSerializer, ProductInfoSerializer, OrderItemSerializer, \
    CategorySerializer, ShopOrderSerializer
from ..tasks import send_email_task


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
            'ordered_items__product_info__shop',
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
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
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
                        {'Status': False, 'Errors': str(error)}, status=400
                    )
                else:
                    objects_created += 1
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': serializer.errors}, status=400
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
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
            )

        basket, _ = Order.objects.get_or_create(
            user_id=request.user.id, state='basket'
        )
        query = Q()
        has_objects_to_delete = False
        for order_item_id in items_list:
            if type(order_item_id) == int:
                query = query | Q(order_id=basket.id, id=order_item_id)
                has_objects_to_delete = True

        if has_objects_to_delete:
            deleted_count = OrderItem.objects.filter(query).delete()[0]
            return JsonResponse(
                {'Status': True, 'Удалено объектов': deleted_count})
        else:
            return JsonResponse(
                {'Status': False, 'Errors': 'Неверный формат запроса'},
                status=400
            )

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
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
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
    Класс для получения и размещения заказов пользователями
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
            'ordered_items__product_info__shop',
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

        try:
            basket = Order.objects.get(user_id=request.user.id, state='basket')
        except Order.DoesNotExist:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Нет заказа со статусом корзины'},
                status=400
            )

        invalid_deliveries = []
        shops = Shop.objects.filter(
            product_infos__ordered_items__order=basket.id
        ).prefetch_related(
            'product_infos__product__category',
            'product_infos__product_parameters__parameter'

        ).annotate(
            shop_sum=Sum(F('product_infos__ordered_items__quantity')
                         * F('product_infos__price'))
        ).distinct()
        for shop in shops:
            shop_data = ShopOrderSerializer(shop, order_id=basket.id).data
            shop_deliveries = Delivery.objects.filter(shop=shop)
            if not shop_deliveries:
                invalid_deliveries.append(f"{shop_data['name']}: "
                                          f"стоимость доставки недоступна.")
            else:
                shop_delivery = shop_deliveries.filter(
                    min_sum__lte=shop_data['shop_sum']
                ).order_by('-min_sum').first()
                if shop_delivery is None:
                    invalid_deliveries.append(
                        f"{shop_data['name']}: сумма заказа меньше минимальной"
                    )
        if invalid_deliveries:
            return JsonResponse(
                {'Status': False, 'Errors': invalid_deliveries}, status=400
            )

        address_id = request.data.get('address_id')
        if not address_id:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
            )
        if type(address_id) != int:
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Неправильно указаны аргументы'},
                status=400
            )

        try:
            basket.address_id = address_id
            basket.state = 'new'
            basket.save()
        except IntegrityError:
            # print(error)
            return JsonResponse(
                {'Status': False, 'Errors': 'Адрес не найден'}, status=400
            )
        else:
            # отправляем письмо пользователю об изменении статуса заказа
            title = f"Обновление статуса заказа {basket.id}"
            message = f'Заказ {basket.id} получил статус Новый.'
            addressee_list = [basket.user.email]
            send_email_task.delay(title, message, addressee_list)

            # отправляем письмо администратору о новом заказе
            title = f"Новый заказ от {basket.user}"
            message = (f'Пользователем {basket.user} оформлен '
                       f'новый заказ {basket.id}.')
            # TODO where to store admin's email?
            addressee_list = ['admin_email@example.com']
            send_email_task.delay(title, message, addressee_list)

            return JsonResponse({'Status': True})
