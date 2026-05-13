import django_filters

from core.filters import BaseDocumentFilter
from .models import FactureAvoir


class FactureAvoirFilter(BaseDocumentFilter):
    numero_field = "numero_avoir"
    req_field = "motif_avoir"
    date_field = "date_avoir"

    motif_avoir = django_filters.CharFilter(field_name="motif_avoir", lookup_expr="exact")
    facture_origine = django_filters.NumberFilter(field_name="facture_origine_id")
    facture_origine_numero = django_filters.CharFilter(
        field_name="facture_origine__numero_facture", lookup_expr="icontains"
    )

    class Meta:
        model = FactureAvoir
        fields = [
            "statut",
            "client_id",
            "motif_avoir",
            "facture_origine",
            "facture_origine_numero",
            "date_after",
            "date_before",
            "total_ttc_apres_remise",
            "total_ttc_apres_remise__gt",
            "total_ttc_apres_remise__gte",
            "total_ttc_apres_remise__lt",
            "total_ttc_apres_remise__lte",
            "total_ttc_apres_remise__ne",
            "lignes_count",
            "lignes_count__gt",
            "lignes_count__gte",
            "lignes_count__lt",
            "lignes_count__lte",
            "lignes_count__ne",
            "client_name",
            "client_name__icontains",
            "client_name__istartswith",
            "client_name__iendswith",
        ]
