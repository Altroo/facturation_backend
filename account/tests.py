import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
class TestAccountAPI:
    def setup_method(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="testuser@example.com", password="securepass123", is_staff=True
        )
        self.token = str(AccessToken.for_user(self.user))
        self.auth_client = APIClient()
        self.auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    # Authentication
    def test_login_success(self):
        url = reverse("account:login")
        response = self.client.post(
            url, {"email": self.user.email, "password": "securepass123"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_login_failure(self):
        url = reverse("account:login")
        response = self.client.post(
            url, {"email": self.user.email, "password": "wrongpass"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout(self):
        url = reverse("account:logout")
        response = self.auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK

    # Email Check
    def test_check_email_exists(self):
        url = reverse("account:check_email")
        response = self.auth_client.post(url, {"email": self.user.email})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data["details"]

    def test_check_email_not_exists(self):
        url = reverse("account:check_email")
        response = self.auth_client.post(url, {"email": "new@example.com"})
        assert response.status_code == status.HTTP_204_NO_CONTENT

    # Password Change
    def test_password_change_success(self):
        url = reverse("account:password_change")
        response = self.auth_client.put(
            url,
            {
                "old_password": "securepass123",
                "new_password": "newsecurepass456",
                "new_password2": "newsecurepass456",
            },
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_password_change_invalid_old(self):
        url = reverse("account:password_change")
        response = self.auth_client.put(
            url,
            {
                "old_password": "wrongpass",
                "new_password": "newsecurepass456",
                "new_password2": "newsecurepass456",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "old_password" in response.data["details"]

    # Password Reset Flow
    def test_send_password_reset_valid_email(self):
        self.user.password_reset_code = "1234"
        self.user.save()
        url = reverse("account:send_password_reset")
        response = self.client.post(url, {"email": self.user.email})
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_send_password_reset_invalid_email(self):
        url = reverse("account:send_password_reset")
        response = self.client.post(url, {"email": "unknown@example.com"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data["details"]

    def test_password_reset_code_check_valid(self):
        self.user.password_reset_code = "1234"
        self.user.save()
        url = reverse("account:password_reset_detail", args=[self.user.email, "1234"])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_password_reset_code_check_invalid(self):
        self.user.password_reset_code = "1234"
        self.user.save()
        url = reverse("account:password_reset_detail", args=[self.user.email, "wrong"])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_reset_put_valid(self):
        self.user.password_reset_code = "1234"
        self.user.save()
        url = reverse("account:password_reset")
        response = self.client.put(
            url,
            {
                "email": self.user.email,
                "code": "1234",
                "new_password": "newpass456",
                "new_password2": "newpass456",
            },
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_password_reset_put_invalid_code(self):
        self.user.password_reset_code = "1234"
        self.user.save()
        url = reverse("account:password_reset")
        response = self.client.put(
            url,
            {
                "email": self.user.email,
                "code": "wrong",
                "new_password": "newpass456",
                "new_password2": "newpass456",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Profile
    def test_get_profile(self):
        url = reverse("account:profil")
        response = self.auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "first_name" in response.data

    def test_patch_profile_name_and_gender(self):
        url = reverse("account:profil")
        response = self.auth_client.patch(
            url, {"first_name": "Al", "last_name": "Tester", "gender": "Homme"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "Al"
        assert response.data["gender"] == "H"

    #  Group
    def test_get_group_titles(self):
        url = reverse("account:group")
        response = self.auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "group_titles" in response.data

    #  Users List
    def test_get_users_list(self):
        url = reverse("account:users")
        response = self.auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list) or "results" in response.data

    #  User Detail
    def test_get_user_detail(self):
        other_user = self.user_model.objects.create_user(
            email="other@example.com", password="pass"
        )
        url = reverse("account:users_detail", args=[other_user.pk])
        response = self.auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == other_user.email

    def test_put_user_update(self):
        other_user = self.user_model.objects.create_user(
            email="other@example.com", password="pass"
        )
        url = reverse("account:users_detail", args=[other_user.pk])
        response = self.auth_client.put(
            url, {"first_name": "Updated", "last_name": "User"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "Updated"

    def test_delete_user(self):
        other_user = self.user_model.objects.create_user(
            email="delete@example.com", password="pass"
        )
        url = reverse("account:users_detail", args=[other_user.pk])
        response = self.auth_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
