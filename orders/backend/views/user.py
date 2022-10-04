from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.http import JsonResponse
from drf_spectacular.utils import (extend_schema_view, extend_schema,
                                   inline_serializer)
from orders.schema import StatusTrueSerializer, StatusFalseSerializer
from rest_framework import viewsets, status, fields
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import ConfirmEmailToken, Address, User
from ..serializers import (UserSerializer, AddressSerializer,
                           UserWithPasswordSerializer)
from ..tasks import send_email_task


class UserViewSet(viewsets.GenericViewSet):
    """
    Viewset для работы с покупателями
    """
    queryset = User.objects.filter(type='buyer')
    serializer_class = UserSerializer
    permission_classes = []

    @extend_schema(
        request=UserWithPasswordSerializer,
        responses={201: StatusTrueSerializer, 400: StatusFalseSerializer}
    )
    @action(methods=['post'], detail=False, permission_classes=[])
    def register(self, request, *args, **kwargs):
        """
        Регистрация покупателей
        """

        # проверяем обязательные аргументы
        required_fields = {'first_name', 'last_name',
                           'email', 'password',
                           'company', 'position'}
        absent_required_fields = required_fields.difference(request.data)
        if absent_required_fields:
            return JsonResponse(
                {'Status': False,
                 'Errors': f"Не указаны необходимые аргументы: "
                           f"{', '.join(absent_required_fields)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # проверяем пароль на сложность
        try:
            validate_password(request.data['password'])
        except Exception as password_error:
            return JsonResponse(
                {'Status': False,
                 'Errors': {'password': list(password_error)}},
                status=status.HTTP_400_BAD_REQUEST
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
                return JsonResponse({'Status': True},
                                    status=status.HTTP_201_CREATED)
            else:
                return JsonResponse(
                    {'Status': False, 'Errors': user_serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

    @extend_schema(
        request=inline_serializer('RegisterConfirmRequestSerializer',
                                  {'email': fields.EmailField(),
                                   'token': fields.CharField()}),
        responses={200: StatusTrueSerializer, 400: StatusFalseSerializer},
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
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(
        request=inline_serializer('LoginRequestSerializer',
                                  {'email': fields.EmailField(),
                                   'password': fields.CharField()}),
        responses={
            200: inline_serializer('LoginStatusTrueSerializer',
                                   {'Status': fields.BooleanField(),
                                    'Token': fields.CharField()}),
            400: StatusFalseSerializer
        },
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
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(request, username=request.data['email'],
                            password=request.data['password'])

        if user is not None:
            if user.is_active:
                token, _ = Token.objects.get_or_create(user=user)

                return JsonResponse({'Status': True, 'Token': token.key})

        return JsonResponse(
            {'Status': False, 'Errors': 'Не удалось авторизовать'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(methods=['get'],
                   description='Получение данных пользователя.')
    @extend_schema(methods=['post'],
                   # TODO serializer without email
                   request=UserWithPasswordSerializer,
                   responses={200: StatusTrueSerializer,
                              400: StatusFalseSerializer},
                   description='Изменение данных пользователя.')
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
                        status=status.HTTP_400_BAD_REQUEST
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
                    {'Status': False, 'Errors': user_serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )


@extend_schema_view(
    list=extend_schema(description='Получение списка адресов '
                                   'текущего пользователя'),
    create=extend_schema(description='Регистрация нового адреса'),
    retrieve=extend_schema(description='Получение адреса по id '
                                       '(только адреса текущего пользователя)'),
    update=extend_schema(description='Замена адреса по id '
                                     '(только адреса текущего пользователя)'),
    partial_update=extend_schema(description='Изменение данных адреса по id '
                                             '(только адреса текущего '
                                             'пользователя)'),
    destroy=extend_schema(description='Удаление адреса по id '
                                      '(только адреса текущего пользователя)')
)
class AddressViewSet(viewsets.ModelViewSet):
    """
    Viewset для работы с адресами покупателя
    """
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Address.objects.none()
        return self.request.user.addresses.all()

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        return serializer_class(*args, user_id=self.request.user.id, **kwargs)
