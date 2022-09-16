import datetime
from distutils.util import strtobool

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Sum, F
from django.http import JsonResponse
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import User, ConfirmEmailToken, Shop, Order, Delivery
from ..serializers import PartnerSerializer, ShopSerializer, \
    PartnerOrderSerializer, DeliverySerializer
from ..tasks import send_email_task


class PartnerViewSet(viewsets.GenericViewSet):
    """
    Viewset для работы с поставщиками
    """
    queryset = User.objects.filter(type='shop')
    serializer_class = PartnerSerializer
    permission_classes = [IsAuthenticated]

    @action(methods=['post'], detail=False, permission_classes=[])
    def register(self, request):
        """
        Регистрация поставщика.
        После регистрации администратору необходимо активировать поставщика
        для начала работы.
        """

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
                 'Errors': {'password': str(password_error)}},
                status=400
            )
        else:
            # проверяем данные для уникальности имени пользователя
            partner_serializer = self.get_serializer(data=request.data)
            if partner_serializer.is_valid():
                # сохраняем пользователя
                user = partner_serializer.save()
                user.set_password(request.data['password'])
                user.save()

                # отправляем письмо с подтверждением почты
                token, _ = ConfirmEmailToken.objects.get_or_create(
                    user_id=user.id
                )
                title = f"Password Reset Token for {token.user.email}"
                message = token.key
                addressee_list = [token.user.email]
                send_email_task.delay(title, message, addressee_list)

                # отправляем письмо администратору
                title = f"Новый поставщик: {user}"
                message = (f"Зарегистрировался новый поставщик: {user}. "
                           f"Для начала работы необходимо его активировать.")
                addressee_list = [settings.ADMIN_EMAIL]
                send_email_task.delay(title, message, addressee_list)

                return JsonResponse({'Status': True})
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': partner_serializer.errors},
                    status=400
                )

    @action(methods=['post'], detail=False, url_path='update')
    def price_info(self, request):
        """
        Получение информации для обновления прайс-листа
        """
        # TODO permission IsShop?
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
        shop_serializer = ShopSerializer(shop, data=data, partial=True)
        if shop_serializer.is_valid():
            shop_serializer.save()

            # отправляем письмо администратору о новом прайс-листе
            title = f"{shop_serializer.data['name']}: обновление прайса"
            message = (f"Пользователь {request.user} сообщил о новом "
                       f"прайс-листе магазина {shop_serializer.data['name']}")
            addressee_list = [settings.ADMIN_EMAIL]
            send_email_task.delay(title, message, addressee_list)

            return JsonResponse({'Status': True})
        else:
            return JsonResponse(
                {'Status': False, 'Errors': shop_serializer.errors},
                status=400
            )

    @action(methods=['get', 'post'], detail=False, url_path='state')
    # получить текущий статус
    def state(self, request):

        if request.user.type != 'shop':
            return JsonResponse(
                {'Status': False, 'Error': 'Только для магазинов'}, status=403
            )

        if request.method == 'GET':
            shop = request.user.shop
            serializer = ShopSerializer(shop)
            return Response(serializer.data['state'])

        else:
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

    @action(detail=False)
    def orders(self, request):
        """
        Просмотр заказов поставщика
        """
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

    @action(methods=['get', 'post'], detail=False)
    def delivery(self, request):
        if request.user.type != 'shop':
            return JsonResponse(
                {'Status': False, 'Error': 'Только для магазинов'}, status=403
            )

        if request.method == 'GET':
            delivery = Delivery.objects.filter(
                shop=request.user.shop
            ).order_by('min_sum')
            serializer = DeliverySerializer(delivery, many=True)
            return Response(serializer.data)
        else:
            delivery = request.data.get('delivery')
            if not delivery:
                return JsonResponse(
                    {'Status': False,
                     'Errors': 'Не указаны все необходимые аргументы'},
                    status=400
                )
            for item in delivery:
                delivery_obj = Delivery.objects.filter(
                    shop=request.user.shop, min_sum=item['min_sum']
                ).first()
                if delivery_obj:
                    delivery_serializer = DeliverySerializer(
                        delivery_obj, data={'cost': item['cost']}, partial=True
                    )
                else:
                    data = {'shop': request.user.shop.id, **item}
                    delivery_serializer = DeliverySerializer(data=data)

                if delivery_serializer.is_valid():
                    delivery_serializer.save()
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse(
                        {'Status': False,
                         'Errors': delivery_serializer.errors},
                        status=400
                    )
