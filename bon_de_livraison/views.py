from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
)
from .filters import BonDeLivraisonFilter
from .models import BonDeLivraison
from .serializers import (
    BonDeLivraisonSerializer,
    BonDeLivraisonDetailSerializer,
    BonDeLivraisonListSerializer,
)
from .utils import get_next_numero_bon_livraison


class BonDeLivraisonListCreateView(BaseDocumentListCreateView):
    model = BonDeLivraison
    filter_class = BonDeLivraisonFilter
    list_serializer_class = BonDeLivraisonListSerializer
    create_serializer_class = BonDeLivraisonSerializer
    detail_serializer_class = BonDeLivraisonDetailSerializer
    document_name = "le bon de livraison"


class BonDeLivraisonDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = BonDeLivraison
    detail_serializer_class = BonDeLivraisonDetailSerializer
    document_name = "bon de livraison"


class GenerateNumeroBonDeLivraisonView(BaseGenerateNumeroView):
    numero_generator = staticmethod(get_next_numero_bon_livraison)
    response_key = "numero_bon_livraison"


class BonDeLivraisonStatusUpdateView(BaseStatusUpdateView):
    model = BonDeLivraison
    document_name = "bon de livraison"
