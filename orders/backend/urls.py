from django.urls import path
from django_rest_passwordreset.views import reset_password_request_token, \
    reset_password_confirm

from .views import PartnerUpdate, RegisterPartner, RegisterAccount, \
    ConfirmAccount, LoginAccount, PartnerState, PartnerOrders, AccountDetails, \
    AddressView, CategoryView, ShopView, ProductInfoView, BasketView, \
    OrderView, DeliveryView

urlpatterns = [
    path('partner/register/', RegisterPartner.as_view(), name='partner-register'),
    path('partner/update/', PartnerUpdate.as_view(), name='partner-update'),
    path('partner/state/', PartnerState.as_view(), name='partner-state'),
    path('partner/orders/', PartnerOrders.as_view(), name='partner-orders'),

    path('user/register/', RegisterAccount.as_view(), name='user-register'),
    path('user/register/confirm/', ConfirmAccount.as_view(), name='user-register-confirm'),
    path('user/login/', LoginAccount.as_view(), name='user-login'),
    path('user/details/', AccountDetails.as_view(), name='user-details'),
    path('user/addresses/', AddressView.as_view(), name='user-contact'),
    path('user/password_reset/', reset_password_request_token, name='password-reset'),
    path('user/password_reset/confirm/', reset_password_confirm, name='password-reset-confirm'),

    path('categories/', CategoryView.as_view(), name='categories'),
    path('shops/', ShopView.as_view(), name='shops'),
    path('products/', ProductInfoView.as_view(), name='products'),
    path('basket/', BasketView.as_view(), name='basket'),
    path('order/', OrderView.as_view(), name='order'),
    path('delivery/', DeliveryView.as_view(), name='delivery'),
]
