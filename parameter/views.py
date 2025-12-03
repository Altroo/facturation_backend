from rest_framework import viewsets, permissions

from .models import (
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    ModeReglement,
)
from .serializers import (
    VilleSerializer,
    MarqueSerializer,
    CategorieSerializer,
    UniteSerializer,
    EmplacementSerializer,
    ModePaiementSerializer,
    ModeRegelementSerializer,
)


class BaseModelViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet with common configuration.
    Provides list, create, retrieve, update, and delete actions.
    """

    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        # Order by descending ID for consistency
        return self.queryset.order_by("-id")


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


class ModeRegelementViewSet(BaseModelViewSet):
    queryset = ModeReglement.objects.all()
    serializer_class = ModeRegelementSerializer
