from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from account.models import Membership
from core.permissions import get_user_role

from .models import (
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    LivrePar,
)
from .serializers import (
    VilleSerializer,
    MarqueSerializer,
    CategorieSerializer,
    UniteSerializer,
    EmplacementSerializer,
    ModePaiementSerializer,
    LivreParSerializer,
)


class BaseModelViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet with common configuration.
    Provides list, create, retrieve, update, and delete actions.

    Permissions:
    - Caissier: Full access (CRUD)
    - Comptable: Read only (GET)
    - Commercial: Read only (GET) - parameters are global master data
    - Lecture: Read only (GET)
    """

    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        # Order by descending ID for consistency
        return self.queryset.order_by("-id")

    def _check_modification_permission(self, action_name: str) -> None:
        """
        Check if user has permission to create/update/delete parameters.
        Only Caissier role is allowed to modify parameters.
        """
        user = self.request.user
        # Get any membership to check role
        membership = Membership.objects.filter(user=user).first()
        if not membership:
            raise PermissionDenied(
                _(
                    f"Vous devez appartenir à une société pour {action_name} des paramètres."
                )
            )

        role = get_user_role(user, membership.company_id)
        if role != "Caissier":
            raise PermissionDenied(
                _(f"Seuls les Caissiers peuvent {action_name} des paramètres.")
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
