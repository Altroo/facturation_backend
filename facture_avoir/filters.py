import django_filters
from django.db.models import Case, CharField, F, When
from rest_framework.exceptions import ValidationError

from core.filters import BaseDocumentFilter, CombinedFiltersMixin
from .models import FactureAvoir


class FactureAvoirFilter(CombinedFiltersMixin, BaseDocumentFilter):
    numero_field = "numero_avoir"
    req_field = "motif_avoir"
    date_field = "date_avoir"

    motif_avoir = django_filters.CharFilter(field_name="motif_avoir", lookup_expr="exact")
    facture_origine = django_filters.NumberFilter(field_name="facture_origine_id")
    facture_origine_numero = django_filters.CharFilter(
        field_name="facture_origine__numero_facture", lookup_expr="icontains"
    )
    facture_origine_numero__icontains = django_filters.CharFilter(
        field_name="facture_origine__numero_facture", lookup_expr="icontains"
    )
    facture_origine_numero__istartswith = django_filters.CharFilter(
        field_name="facture_origine__numero_facture", lookup_expr="istartswith"
    )
    facture_origine_numero__iendswith = django_filters.CharFilter(
        field_name="facture_origine__numero_facture", lookup_expr="iendswith"
    )
    ordering = django_filters.CharFilter(method="filter_ordering")

    def filter_ordering(self, queryset, _name, value):
        fields = {
            "numero_avoir": "numero_avoir",
            "client_name": "_client_display_name",
            "motif_avoir": "motif_avoir",
            "facture_origine_numero": "facture_origine__numero_facture",
            "statut": "statut",
            "total_ttc_apres_remise": "total_ttc_apres_remise",
            "lignes_count": "lignes_count",
            "date_avoir": "date_avoir",
        }
        requested = value.split(",")
        if any(field.lstrip("-") not in fields for field in requested):
            raise ValidationError({"ordering": "Invalid ordering field."})
        if any(field.lstrip("-") == "client_name" for field in requested):
            queryset = queryset.annotate(
                _client_display_name=Case(
                    When(client__client_type="PM", then=F("client__raison_sociale")),
                    default=self._client_full_name_expression(),
                    output_field=CharField(),
                )
            )
        if any(field.lstrip("-") == "lignes_count" for field in requested):
            queryset = self._annotate_lignes_count(queryset)
        # Keep pagination stable when two documents share the selected value.
        return queryset.order_by(
            *[
                ("-" if field.startswith("-") else "") + fields[field.lstrip("-")]
                for field in requested
            ],
            "-id",
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
