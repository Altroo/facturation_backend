from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseConversionView,
)
from facture_client.utils import get_next_numero_facture_client
from facture_proforma.utils import get_next_numero_facture_pro_forma
from .filters import DeviFilter
from .models import Devi
from .serializers import (
    DeviSerializer,
    DeviDetailSerializer,
    DeviListSerializer,
)
from .utils import get_next_numero_devis


class DeviListCreateView(BaseDocumentListCreateView):
    model = Devi
    filter_class = DeviFilter
    list_serializer_class = DeviListSerializer
    create_serializer_class = DeviSerializer
    detail_serializer_class = DeviDetailSerializer
    document_name = "le devis"


class DeviDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = Devi
    detail_serializer_class = DeviDetailSerializer
    document_name = "devis"


class GenerateNumeroDevisView(BaseGenerateNumeroView):
    numero_generator = staticmethod(get_next_numero_devis)
    response_key = "numero_devis"


class DeviStatusUpdateView(BaseStatusUpdateView):
    model = Devi
    document_name = "devis"


class DeviConvertToFactureProformaView(BaseConversionView):
    model = Devi
    document_name = "devis"
    numero_generator = staticmethod(get_next_numero_facture_pro_forma)
    conversion_method = "convert_to_facture_proforma"


class DeviConvertToFactureClientView(BaseConversionView):
    model = Devi
    document_name = "devis"
    numero_generator = staticmethod(get_next_numero_facture_client)
    conversion_method = "convert_to_facture_client"
