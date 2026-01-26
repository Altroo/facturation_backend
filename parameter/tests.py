import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Membership, Role
from company.models import Company
from parameter.models import (
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    LivrePar,
)


@pytest.mark.django_db
class BaseAPITest:
    model = None
    basename = None
    field = "nom"

    def setup_method(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="test@example.com", password="pass"
        )

        # Create company and Caissier role membership
        self.caissier_role, _ = Role.objects.get_or_create(
            name="Caissier",
        )
        self.company = Company.objects.create(
            raison_sociale="TestCompany", ICE="ICE123", nbr_employe="1 à 5"
        )
        Membership.objects.create(
            user=self.user, company=self.company, role=self.caissier_role
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # create one instance
        self.obj = self.model.objects.create(
            **{self.field: f"{self.basename.title()}1"}
        )

    @staticmethod
    def _get_results(response):
        return response.data

    def test_list(self):
        url = reverse(f"parameter:{self.basename}-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        results = self._get_results(response)
        assert any(o[self.field] == getattr(self.obj, self.field) for o in results)

    def test_create(self):
        url = reverse(f"parameter:{self.basename}-list")
        payload = {self.field: f"{self.basename.title()}2"}
        response = self.client.post(url, payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert self.model.objects.filter(**{self.field: payload[self.field]}).exists()

    def test_get_detail(self):
        url = reverse(f"parameter:{self.basename}-detail", args=[self.obj.id])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data[self.field] == getattr(self.obj, self.field)

    def test_update(self):
        url = reverse(f"parameter:{self.basename}-detail", args=[self.obj.id])
        payload = {self.field: f"{self.basename.title()}Updated"}
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_200_OK
        self.obj.refresh_from_db()
        assert getattr(self.obj, self.field) == payload[self.field]

    def test_delete(self):
        url = reverse(f"parameter:{self.basename}-detail", args=[self.obj.id])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not self.model.objects.filter(id=self.obj.id).exists()

    def test_requires_authentication(self):
        unauth = APIClient()
        list_url = reverse(f"parameter:{self.basename}-list")
        detail_url = reverse(f"parameter:{self.basename}-detail", args=[self.obj.id])
        assert unauth.get(list_url).status_code == status.HTTP_401_UNAUTHORIZED
        assert (
            unauth.post(list_url, {self.field: "X"}).status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        assert unauth.get(detail_url).status_code == status.HTTP_401_UNAUTHORIZED
        assert (
            unauth.put(detail_url, {self.field: "Y"}).status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        assert unauth.delete(detail_url).status_code == status.HTTP_401_UNAUTHORIZED

    def test_detail_404(self):
        url = reverse(f"parameter:{self.basename}-detail", args=[999999])
        assert self.client.get(url).status_code == status.HTTP_404_NOT_FOUND
        assert self.client.delete(url).status_code == status.HTTP_404_NOT_FOUND

    def test_duplicate_name(self):
        other = self.model.objects.create(**{self.field: f"{self.basename.title()}Dup"})
        url = reverse(f"parameter:{self.basename}-detail", args=[other.id])
        payload = {self.field: getattr(self.obj, self.field)}  # duplicate
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert self.field in response.data["details"]

    def test_empty_name(self):
        url = reverse(f"parameter:{self.basename}-detail", args=[self.obj.id])
        payload = {self.field: ""}
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert self.field in response.data["details"]
        self.obj.refresh_from_db()
        assert getattr(self.obj, self.field) != ""

    def test_serializer_fields_shape(self):
        url = reverse(f"parameter:{self.basename}-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        results = self._get_results(response)
        for item in results:
            assert set(item.keys()) == {"id", self.field}


# --- Concrete test classes for each model ---
class TestVilleAPI(BaseAPITest):
    model = Ville
    basename = "ville"


class TestMarqueAPI(BaseAPITest):
    model = Marque
    basename = "marque"


class TestCategorieAPI(BaseAPITest):
    model = Categorie
    basename = "categorie"


class TestUniteAPI(BaseAPITest):
    model = Unite
    basename = "unite"


class TestEmplacementAPI(BaseAPITest):
    model = Emplacement
    basename = "emplacement"


class TestModePaiementAPI(BaseAPITest):
    model = ModePaiement
    basename = "mode_paiement"


class TestLivreParAPI(BaseAPITest):
    model = LivrePar
    basename = "livre_par"


@pytest.mark.django_db
class TestParameterModelsExtra:
    """Extra tests for parameter models __str__ methods."""

    def test_mode_paiement_str(self):
        """Test ModePaiement __str__."""
        obj = ModePaiement.objects.create(nom="Test Payment Extra")
        assert str(obj) == "Test Payment Extra"

    def test_ville_str(self):
        """Test Ville __str__."""
        obj = Ville.objects.create(nom="Test City Extra")
        assert str(obj) == "Test City Extra"

    def test_categorie_str(self):
        """Test Categorie __str__."""
        obj = Categorie.objects.create(nom="Test Cat Extra")
        assert str(obj) == "Test Cat Extra"

    def test_marque_str(self):
        """Test Marque __str__."""
        obj = Marque.objects.create(nom="Test Brand Extra")
        assert str(obj) == "Test Brand Extra"

    def test_unite_str(self):
        """Test Unite __str__."""
        obj = Unite.objects.create(nom="KG Extra")
        assert str(obj) == "KG Extra"

    def test_emplacement_str(self):
        """Test Emplacement __str__."""
        obj = Emplacement.objects.create(nom="Warehouse A Extra")
        assert str(obj) == "Warehouse A Extra"

    def test_livre_par_str(self):
        """Test LivrePar __str__."""
        obj = LivrePar.objects.create(nom="Delivery Person Extra")
        assert str(obj) == "Delivery Person Extra"
