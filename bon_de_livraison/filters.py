import django_filters
from django.db.models import Case, CharField, F, When
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from core.filters import (
    BaseDocumentFilter,
    CommaSeparatedIDsFilter,
    CombinedFiltersMixin,
)
from .models import BonDeLivraison


class BonDeLivraisonFilter(CombinedFiltersMixin, BaseDocumentFilter):
    """Filter for BonDeLivraison model."""

    numero_field = "numero_bon_livraison"
    req_field = "numero_bon_commande_client"
    date_field = "date_bon_livraison"

    # Chip select multi-ID filter
    livre_par_ids = CommaSeparatedIDsFilter(
        field_name="livre_par_id", label=_("Livré par IDs")
    )

    ordering = django_filters.CharFilter(method="filter_ordering")

    def filter_ordering(self, queryset, _name, value):
        fields = {
            "numero_bon_livraison": "numero_bon_livraison",
            "client_name": "_client_display_name",
            "numero_bon_commande_client": "numero_bon_commande_client",
            "livre_par_name": "livre_par__nom",
            "statut": "statut",
            "total_ttc_apres_remise": "total_ttc_apres_remise",
            "lignes_count": "lignes_count",
            "date_bon_livraison": "date_bon_livraison",
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
        model = BonDeLivraison
        fields = [
            "statut",
            "client_id",
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
