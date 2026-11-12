from typing import cast

from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.db import transaction
from .protection import ensure_parameter_unused

from account.models import Membership, CustomUser
from core.constants import ROLE_CAISSIER
from core.permissions import get_user_role
from .models import (
    Incoterm,
    OrigineMarchandise,
    NatureMarchandise,
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    LivrePar,
)
from .serializers import (
    IncotermSerializer,
    OrigineMarchandiseSerializer,
    NatureMarchandiseSerializer,
    VilleSerializer,
    MarqueSerializer,
    CategorieSerializer,
    UniteSerializer,
    EmplacementSerializer,
    ModePaiementSerializer,
    LivreParSerializer,
)


class BaseModelViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Base ViewSet with common configuration.
    Provides list, create, update, and delete actions.
    Filters by company_id query parameter.

    Permissions:
    - Caissier: Full access (CRUD)
    - Comptable: Read only (GET)
    - Commercial: Read only (GET)
    - Lecture: Read only (GET)
    """

    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        queryset = self.queryset
        if queryset is None:
            raise AssertionError(f"{type(self).__name__} must define queryset")
        qs = queryset.order_by("-id")
        company_id = self.request.query_params.get("company_id")
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs.filter(
            company_id__in=Membership.objects.filter(user=self.request.user).values(
                "company_id"
            )
        )

    def _check_modification_permission(self, action_name: str) -> None:
        """
        Check if user has permission to create/update/delete parameters.
        Only Caissier role is allowed to modify parameters.
        Validates membership for the company being modified.
        """
        user = cast(CustomUser, self.request.user)
        instance = self.get_object() if self.detail else None
        company_id = (
            instance.company_id if instance else self.request.data.get("company")
        )
        if instance and str(self.request.data.get("company", company_id)) != str(
            company_id
        ):
            raise PermissionDenied(
                "Un paramètre ne peut pas être déplacé vers une autre société."
            )
        if company_id:
            membership = Membership.objects.filter(
                user=user, company_id=company_id
            ).first()
        else:
            membership = Membership.objects.filter(user=user).first()
        if not membership:
            raise PermissionDenied(
                _(
                    "Vous devez appartenir à une société pour %(action_name)s des paramètres."
                )
                % {"action_name": action_name}
            )

        role = get_user_role(user, membership.company_id)
        if role != ROLE_CAISSIER:
            raise PermissionDenied(
                _("Seuls les Caissiers peuvent %(action_name)s des paramètres.")
                % {"action_name": action_name}
            )

    def create(self, request, *args, **kwargs):
        self._check_modification_permission("créer")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._check_modification_permission("modifier")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._check_modification_permission("modifier")
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._check_modification_permission("supprimer")
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        with transaction.atomic():
            locked = type(instance).objects.select_for_update().get(pk=instance.pk)
            ensure_parameter_unused(locked)
            try:
                locked.delete()
            except ProtectedError:
                raise ValidationError(
                    {
                        "nom": "Cette valeur est déjà utilisée et ne peut pas être supprimée."
                    }
                )


class IncotermViewSet(BaseModelViewSet):
    queryset = Incoterm.objects.all()
    serializer_class = IncotermSerializer

    def _check_modification_permission(self, action_name):
        instance = self.get_object() if self.detail else None
        company_id = (
            instance.company_id if instance else self.request.data.get("company")
        )
        if instance and str(self.request.data.get("company", company_id)) != str(
            company_id
        ):
            raise PermissionDenied(
                "Une valeur ne peut pas être déplacée vers une autre société."
            )
        if not Membership.objects.filter(
            user=self.request.user,
            company_id=company_id,
            role__name__in=("Caissier", "Logistique"),
        ).exists():
            raise PermissionDenied(
                "Seuls les Caissiers et la Logistique de cette société peuvent gérer ces listes."
            )


class OrigineMarchandiseViewSet(IncotermViewSet):
    queryset = OrigineMarchandise.objects.all()
    serializer_class = OrigineMarchandiseSerializer


class NatureMarchandiseViewSet(IncotermViewSet):
    queryset = NatureMarchandise.objects.all()
    serializer_class = NatureMarchandiseSerializer


class VilleViewSet(BaseModelViewSet):
    queryset = Ville.objects.all()
    serializer_class = VilleSerializer


class MarqueViewSet(BaseModelViewSet):
    queryset = Marque.objects.all()
    serializer_class = MarqueSerializer


class CategorieViewSet(BaseModelViewSet):
    queryset = Categorie.objects.all()
    serializer_class = CategorieSerializer


class UniteViewSet(BaseModelViewSet):
    queryset = Unite.objects.all()
    serializer_class = UniteSerializer


class EmplacementViewSet(BaseModelViewSet):
    queryset = Emplacement.objects.all()
    serializer_class = EmplacementSerializer


class ModePaiementViewSet(BaseModelViewSet):
    queryset = ModePaiement.objects.all()
    serializer_class = ModePaiementSerializer


class LivreParViewSet(BaseModelViewSet):
    queryset = LivrePar.objects.all()
    serializer_class = LivreParSerializer
