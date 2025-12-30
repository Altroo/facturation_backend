from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseConversionView,
)
from bon_de_livraison.utils import get_next_numero_bon_livraison
from .filters import FactureClientFilter
from .models import FactureClient
from .serializers import (
    FactureClientSerializer,
    FactureClientDetailSerializer,
    FactureClientListSerializer,
)
from .utils import get_next_numero_facture_client


class FactureClientListCreateView(BaseDocumentListCreateView):
    model = FactureClient
    filter_class = FactureClientFilter
    list_serializer_class = FactureClientListSerializer
    create_serializer_class = FactureClientSerializer
    detail_serializer_class = FactureClientDetailSerializer
    document_name = "la facture client"


class FactureClientDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = FactureClient
    detail_serializer_class = FactureClientDetailSerializer
    document_name = "facture client"


class GenerateNumeroFactureView(BaseGenerateNumeroView):
    numero_generator = staticmethod(get_next_numero_facture_client)
    response_key = "numero_facture"


class FactureClientStatusUpdateView(BaseStatusUpdateView):
    model = FactureClient
    document_name = "facture client"


class FactureClientConvertToBonDeLivraisonView(BaseConversionView):
    model = FactureClient
    document_name = "facture client"
    numero_generator = staticmethod(get_next_numero_bon_livraison)
    conversion_method = "convert_to_bon_de_livraison"
    numero_param_name = "numero_bon_livraison"
