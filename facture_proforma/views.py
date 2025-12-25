from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseConversionView,
)
from facture_client.utils import get_next_numero_facture_client
from .filters import FactureProFormaFilter
from .models import FactureProForma
from .serializers import (
    FactureProformaSerializer,
    FactureProformaDetailSerializer,
    FactureProformaListSerializer,
)
from .utils import get_next_numero_facture_pro_forma


class FactureProFormaListCreateView(BaseDocumentListCreateView):
    model = FactureProForma
    filter_class = FactureProFormaFilter
    list_serializer_class = FactureProformaListSerializer
    create_serializer_class = FactureProformaSerializer
    detail_serializer_class = FactureProformaDetailSerializer
    document_name = "la facture proforma"


class FactureProFormaDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = FactureProForma
    detail_serializer_class = FactureProformaDetailSerializer
    document_name = "facture proforma"


class GenerateNumeroFactureView(BaseGenerateNumeroView):
    numero_generator = staticmethod(get_next_numero_facture_pro_forma)
    response_key = "numero_facture"


class FactureProFormaStatusUpdateView(BaseStatusUpdateView):
    model = FactureProForma
    document_name = "facture proforma"


class FactureProFormaConvertToFactureClientView(BaseConversionView):
    model = FactureProForma
    document_name = "facture pro-forma"
    numero_generator = staticmethod(get_next_numero_facture_client)
    conversion_method = "convert_to_facture_client"
