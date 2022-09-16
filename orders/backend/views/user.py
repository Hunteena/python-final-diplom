from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    ConfirmEmailToken, Address, User
)
from ..serializers import UserSerializer, AddressSerializer
from ..tasks import send_email_task


class UserViewSet(viewsets.GenericViewSet):
    """
    Viewset для работы с покупателями
    """
    queryset = User.objects.filter(type='buyer')
    serializer_class = UserSerializer
    permission_classes = []

    @action(methods=['post'], detail=False, permission_classes=[])
    def register(self, request, *args, **kwargs):
        """
        Регистрация покупателей
        """

        # проверяем обязательные аргументы
        required_fields = {'first_name', 'last_name',
                           'email', 'password',
                           'company', 'position'}
        if not required_fields.issubset(request.data):
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
            user_serializer = self.get_serializer(data=request.data)
            if user_serializer.is_valid():
                # сохраняем пользователя
                user = user_serializer.save()
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
                return JsonResponse({'Status': True})
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': user_serializer.errors},
                    status=400
                )

    @action(methods=['post'], detail=False, url_path='register/confirm')
    def register_confirm(self, request, *args, **kwargs):
        """
        Подтверждение почтового адреса
        """

        # проверяем обязательные аргументы
        if not {'email', 'token'}.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
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
                 'Errors': 'Неправильно указан токен или email'},
                status=400
            )

    @action(methods=['post'], detail=False)
    def login(self, request, *args, **kwargs):
        """
        Авторизация пользователей
        """

        if not {'email', 'password'}.issubset(request.data):
            return JsonResponse(
                {'Status': False,
                 'Errors': 'Не указаны все необходимые аргументы'},
                status=400
            )

        user = authenticate(request, username=request.data['email'],
                            password=request.data['password'])

        if user is not None:
            if user.is_active:
                token, _ = Token.objects.get_or_create(user=user)

                return JsonResponse({'Status': True, 'Token': token.key})

        return JsonResponse(
            {'Status': False, 'Errors': 'Не удалось авторизовать'}, status=400
        )

    @action(methods=['get', 'post'], detail=False, url_path='details',
            permission_classes=[IsAuthenticated])
    def account_details(self, request, *args, **kwargs):
        """
        Получение и изменение данных пользователя
        """
        if request.method == 'GET':
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)
        else:
            if 'password' in request.data:
                errors = {}
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
                    request.user.set_password(request.data['password'])

            # проверяем остальные данные
            user_serializer = self.get_serializer(request.user,
                                                  data=request.data,
                                                  partial=True)
            if user_serializer.is_valid():
                user_serializer.save()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': user_serializer.errors}, status=400
                )


class AddressViewSet(viewsets.ModelViewSet):
    """
    Viewset для работы с адресами покупателя
    """
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.request.user.addresses.all()

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        return serializer_class(*args, user_id=self.request.user.id, **kwargs)

# class AddressView(APIView):
#     """
#     Класс для работы с адресами покупателей
#     """
#
#     # получить мои адреса
#     def get(self, request, *args, **kwargs):
#         if not request.user.is_authenticated:
#             return JsonResponse({'Status': False, 'Error': 'Log in required'},
#                                 status=403)
#         address = Address.objects.filter(user_id=request.user.id)
#         serializer = AddressSerializer(address, many=True)
#         return Response(serializer.data)
#
#     # добавить новый адрес
#     def post(self, request, *args, **kwargs):
#         if not request.user.is_authenticated:
#             return JsonResponse({'Status': False, 'Error': 'Log in required'},
#                                 status=403)
#
#         if not {'city', 'street'}.issubset(request.data):
#             return JsonResponse(
#                 {'Status': False,
#                  'Errors': 'Не указаны все необходимые аргументы'},
#                 status=400
#             )
#
#         # request.data._mutable = True
#         request.data.update({'user': request.user.id})
#         serializer = AddressSerializer(data=request.data)
#
#         if serializer.is_valid():
#             serializer.save()
#             return JsonResponse({'Status': True})
#         else:
#             return JsonResponse({'Status': False, 'Errors': serializer.errors},
#                                 status=400)
#
#     # удалить адрес
#     def delete(self, request, *args, **kwargs):
#         if not request.user.is_authenticated:
#             return JsonResponse({'Status': False, 'Error': 'Log in required'},
#                                 status=403)
#
#         items_list = request.data.get('items')
#         if not items_list:
#             return JsonResponse(
#                 {'Status': False,
#                  'Errors': 'Не указаны все необходимые аргументы'},
#                 status=400
#             )
#
#         query = Q()
#         has_objects_to_delete = False
#         for address_id in items_list:
#             if type(address_id) == int:
#                 query = query | Q(user_id=request.user.id, id=address_id)
#                 has_objects_to_delete = True
#
#         if has_objects_to_delete:
#             deleted = Address.objects.filter(query).delete()
#             return JsonResponse(
#                 {'Status': True, 'Удалено объектов': deleted[0]})
#         else:
#             return JsonResponse(
#                 {'Status': False,
#                  'Errors': 'Неправильный формат запроса'},
#                 status=400
#             )
#
#     # редактировать адрес
#     def put(self, request, *args, **kwargs):
#         if not request.user.is_authenticated:
#             return JsonResponse({'Status': False, 'Error': 'Log in required'},
#                                 status=403)
#
#         if 'id' not in request.data:
#             return JsonResponse(
#                 {'Status': False,
#                  'Errors': 'Не указаны все необходимые аргументы'},
#                 status=400
#             )
#
#         if type(request.data['id']) != int:
#             return JsonResponse(
#                 {'Status': False,
#                  'Errors': 'Неправильный формат запроса'},
#                 status=400
#             )
#
#         address = Address.objects.filter(
#             id=request.data['id'], user_id=request.user.id
#         ).first()
#         if not address:
#             return JsonResponse(
#                 {'Status': False,
#                  'Errors': 'Нет адреса с таким id'},
#                 status=400
#             )
#
#         request.data.update({'user': request.user.id})
#         serializer = AddressSerializer(
#             address, data=request.data, partial=True
#         )
#         if serializer.is_valid():
#             serializer.save()
#             return JsonResponse({'Status': True})
#         else:
#             return JsonResponse(
#                 {'Status': False, 'Errors': serializer.errors}, status=400
#             )
