from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
)
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
