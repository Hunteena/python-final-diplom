from django.conf import settings
from django.core.mail import EmailMultiAlternatives
# from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created

from .models import ConfirmEmailToken, User, Order, STATE_CHOICES

new_user_registered = Signal()
order_state_changed = Signal()
price_list_updated = Signal()


@receiver(new_user_registered)
def new_user_registered_signal(user_id, **kwargs):
    """
    отправляем письмо с подтверждением почты
    """
    # send an e-mail to the user
    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user_id)

    msg = EmailMultiAlternatives(
        # title:
        f"Password Reset Token for {token.user.email}",
        # message:
        token.key,
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [token.user.email]
    )
    msg.send()


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token,
                                 **kwargs):
    """
    Отправляем письмо с токеном для сброса пароля
    When a token is created, an e-mail needs to be sent to the user
    :param sender: View Class that sent the signal
    :param instance: View Instance that sent the signal
    :param reset_password_token: Token Model Object
    :param kwargs:
    :return:
    """
    # send an e-mail to the user

    msg = EmailMultiAlternatives(
        # title:
        f"Password Reset Token for {reset_password_token.user}",
        # message:
        reset_password_token.key,
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [reset_password_token.user.email]
    )
    msg.send()


@receiver(order_state_changed)
def order_state_changed_signal(user_id, order_id, state, **kwargs):
    """
    отправяем письмо при изменении статуса заказа
    """
    # send an e-mail to the user
    user = User.objects.get(id=user_id)
    rus_state = ''
    for state_tuple in STATE_CHOICES:
        if state_tuple[0] == state:
            rus_state = state_tuple[1]
            break

    msg = EmailMultiAlternatives(
        # title:
        f"Обновление статуса заказа",
        # message:
        f'Заказ {order_id} получил статус {rus_state}.',
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [user.email]
    )
    msg.send()

    if state == 'new':
        msg = EmailMultiAlternatives(
            # title:
            f"Новый заказ от {user}",
            # message:
            f'Пользователем {user} оформлен новый заказ {order_id}.',
            # from:
            settings.EMAIL_HOST_USER,
            # to:
            ['admin_email@example.com']  # TODO where to store admin's email?
        )
        msg.send()


@receiver(price_list_updated)
def price_list_updated_signal(user, shop_name, **kwargs):
    # send an e-mail to the user

    msg = EmailMultiAlternatives(
        # title:
        f"{shop_name}: обновление прайса",
        # message:
        f"Пользователь {user} сообщил о новом прайс-листе магазина {shop_name}",
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [user.email]
    )
    msg.send()
