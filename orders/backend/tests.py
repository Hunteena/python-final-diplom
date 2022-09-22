import pytest
from rest_framework.test import APIClient
from rest_framework import status

from .models import User

PATH_PREFIX = 'http://127.0.0.1:8000/api/v1/'


def full_path(relative_path: str) -> str:
    return PATH_PREFIX + relative_path


valid_partner_data = {"email": "partner_email@example.com",
                      "password": "lkajdhfkljdshf", "company": "Я и Ко",
                      "first_name": "Иван", "last_name": "Иванов",
                      "phone": "3516817861"}

test_data_register_partner = [
    [valid_partner_data,
     status.HTTP_201_CREATED, 'Регистрация с корректными данными'],
    [{key: valid_partner_data[key] for key in ['email', 'password']},
     status.HTTP_400_BAD_REQUEST, 'Регистрация с неполными данными'],
    [{**valid_partner_data, **dict(email="partner_email")},
     status.HTTP_400_BAD_REQUEST, 'Некорректный email'],
    [{**valid_partner_data, **dict(password="1")},
     status.HTTP_400_BAD_REQUEST, 'Некорректный пароль'],
]

test_data_only_for_shops = [
    ['partner/update/', 'post'],
    ['partner/state/', 'get'], ['partner/state/', 'post'],
    ['partner/orders/', 'get'],
    ['partner/delivery/', 'get'], ['partner/delivery/', 'post']
]

# TODO create temporary file and url
valid_update_data = {
    "file": '/home/nina/Projects/python-final-diplom/data/shop1.yaml',
    "url": "https://raw.githubusercontent.com/Hunteena/python-final-diplom/master/data/shop1.yaml"
}
test_data_update_price_info = [
    [valid_update_data['file'], valid_update_data['url'],
     status.HTTP_200_OK, 'Корректные данные'],
    [valid_update_data['file'], None, status.HTTP_200_OK, 'Только файл'],
    [None, valid_update_data['url'], status.HTTP_200_OK, 'Только url'],
    [None, None, status.HTTP_400_BAD_REQUEST, 'Данные не переданы'],
]


@pytest.mark.django_db
class TestPartner:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def valid_user(self):
        return User.objects.create_user(valid_partner_data['email'],
                                        valid_partner_data['password'])

    @pytest.fixture
    def valid_partner(self, valid_user):
        valid_user.type = 'shop'
        valid_user.save()
        return valid_user

    @pytest.mark.parametrize('data, expected_status, description',
                             test_data_register_partner)
    def test_register_partner(self, api_client,
                              data, expected_status, description):
        count = User.objects.count()

        response = api_client.post(full_path("partner/register/"), data=data)

        assert response.status_code == expected_status, description
        if response.status_code == status.HTTP_201_CREATED:
            assert User.objects.count() == count + 1, \
                'Количество пользователей должно увеличиться'

    def test_register_partner_with_existing_email(self, api_client,
                                                  valid_user):
        response = api_client.post(full_path("partner/register/"),
                                   data=valid_partner_data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST, \
            'Email уже зарегистрирован'

    @pytest.mark.parametrize('path, method', test_data_only_for_shops)
    def test_only_for_shops(self, api_client, valid_user, path, method):
        api_client.force_authenticate(valid_user)

        response = getattr(api_client, method)(full_path(path))

        assert response.status_code == status.HTTP_403_FORBIDDEN, \
            "Не является магазином"

    @pytest.mark.parametrize('file_path, url, expected_status, description',
                             test_data_update_price_info)
    def test_price_info(self, api_client, valid_partner,
                        file_path, url, expected_status, description):
        api_client.force_authenticate(valid_partner)

        if file_path:
            with open(file_path, 'rb') as fp:
                response = api_client.post(
                    full_path('partner/update/'), {'file': fp},
                    format='multipart'
                )
        else:
            response = api_client.post(
                full_path('partner/update/'), {"url": url}
            )

        print(response.content)
        assert response.status_code == expected_status, description
