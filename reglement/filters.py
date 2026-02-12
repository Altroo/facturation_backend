import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, FloatField, F
from django.db.utils import DatabaseError

from .models import Reglement
from core.filters import IsEmptyAutoMixin, CommaSeparatedIDsFilter


class ReglementFilter(IsEmptyAutoMixin, django_filters.FilterSet):
    """
    Filter class for Reglement model.

    Supports:
    - Global search across libelle, facture numero, client name
    - Filter by statut, facture_client_id, mode_reglement
    - Filter by date_reglement and date_echeance (exact, gte, lte)
    """

    search = django_filters.CharFilter(method="global_search", label="Search")
    statut = django_filters.CharFilter(method="filter_statut", label="Status")
    facture_client_id = django_filters.NumberFilter(
        field_name="facture_client__id", label="Facture Client ID"
    )
    mode_reglement_id = django_filters.NumberFilter(
        field_name="mode_reglement__id", label="Mode Règlement ID"
    )

    # Chip select multi-ID filter
    mode_reglement_ids = CommaSeparatedIDsFilter(
        field_name="mode_reglement_id", label="Mode Règlement IDs"
    )
    date_reglement = django_filters.DateFilter(
        field_name="date_reglement", label="Date de règlement"
    )
    date_reglement_gte = django_filters.DateFilter(
        field_name="date_reglement", lookup_expr="gte", label="Date de règlement (>=)"
    )
    date_reglement_lte = django_filters.DateFilter(
        field_name="date_reglement", lookup_expr="lte", label="Date de règlement (<=)"
    )
    date_reglement_after = django_filters.DateFilter(
        field_name="date_reglement", lookup_expr="gte", label="Date de règlement (>=)"
    )
    date_reglement_before = django_filters.DateFilter(
        field_name="date_reglement", lookup_expr="lte", label="Date de règlement (<=)"
    )
    date_echeance = django_filters.DateFilter(
        field_name="date_echeance", label="Date d'échéance"
    )
    date_echeance_gte = django_filters.DateFilter(
        field_name="date_echeance", lookup_expr="gte", label="Date d'échéance (>=)"
    )
    date_echeance_lte = django_filters.DateFilter(
        field_name="date_echeance", lookup_expr="lte", label="Date d'échéance (<=)"
    )
    date_echeance_after = django_filters.DateFilter(
        field_name="date_echeance", lookup_expr="gte", label="Date d'échéance (>=)"
    )
    date_echeance_before = django_filters.DateFilter(
        field_name="date_echeance", lookup_expr="lte", label="Date d'échéance (<=)"
    )

    # Numeric field filters for montant
    montant = django_filters.NumberFilter(field_name="montant", lookup_expr="exact")
    montant__gt = django_filters.NumberFilter(field_name="montant", lookup_expr="gt")
    montant__gte = django_filters.NumberFilter(field_name="montant", lookup_expr="gte")
    montant__lt = django_filters.NumberFilter(field_name="montant", lookup_expr="lt")
    montant__lte = django_filters.NumberFilter(field_name="montant", lookup_expr="lte")
    montant__ne = django_filters.NumberFilter(field_name="montant", exclude=True)

    # Text lookup filters for libelle
    libelle__icontains = django_filters.CharFilter(field_name="libelle", lookup_expr="icontains")
    libelle__istartswith = django_filters.CharFilter(field_name="libelle", lookup_expr="istartswith")
    libelle__iendswith = django_filters.CharFilter(field_name="libelle", lookup_expr="iendswith")
    libelle = django_filters.CharFilter(field_name="libelle", lookup_expr="exact")

    # Text lookup filters for facture_client_numero (mapped to facture_client__numero_facture)
    facture_client_numero__icontains = django_filters.CharFilter(field_name="facture_client__numero_facture", lookup_expr="icontains")
    facture_client_numero__istartswith = django_filters.CharFilter(field_name="facture_client__numero_facture", lookup_expr="istartswith")
    facture_client_numero__iendswith = django_filters.CharFilter(field_name="facture_client__numero_facture", lookup_expr="iendswith")
    facture_client_numero = django_filters.CharFilter(field_name="facture_client__numero_facture", lookup_expr="exact")

    # Text lookup filters for client_name (mapped to facture_client__client__raison_sociale)
    client_name__icontains = django_filters.CharFilter(field_name="facture_client__client__raison_sociale", lookup_expr="icontains")
    client_name__istartswith = django_filters.CharFilter(field_name="facture_client__client__raison_sociale", lookup_expr="istartswith")
    client_name__iendswith = django_filters.CharFilter(field_name="facture_client__client__raison_sociale", lookup_expr="iendswith")
    client_name = django_filters.CharFilter(field_name="facture_client__client__raison_sociale", lookup_expr="exact")

    # Text lookup filters for mode_reglement_name (mapped to mode_reglement__nom)
    mode_reglement_name__icontains = django_filters.CharFilter(field_name="mode_reglement__nom", lookup_expr="icontains")
    mode_reglement_name__istartswith = django_filters.CharFilter(field_name="mode_reglement__nom", lookup_expr="istartswith")
    mode_reglement_name__iendswith = django_filters.CharFilter(field_name="mode_reglement__nom", lookup_expr="iendswith")
    mode_reglement_name = django_filters.CharFilter(field_name="mode_reglement__nom", lookup_expr="exact")

    class Meta:
        model = Reglement
        fields = [
            "statut",
            "facture_client_id",
            "mode_reglement_id",
            "date_reglement",
            "date_echeance",
            "montant", "montant__gt", "montant__gte", "montant__lt", "montant__lte", "montant__ne",
            "libelle", "libelle__icontains", "libelle__istartswith", "libelle__iendswith",
            "facture_client_numero", "facture_client_numero__icontains", "facture_client_numero__istartswith", "facture_client_numero__iendswith",
            "client_name", "client_name__icontains", "client_name__istartswith", "client_name__iendswith",
            "mode_reglement_name", "mode_reglement_name__icontains", "mode_reglement_name__istartswith", "mode_reglement_name__iendswith",
        ]

    @staticmethod
    def filter_statut(queryset, _name, value):
        """Filter by statut (case-insensitive)."""
        if not value:
            return queryset
        return queryset.filter(statut__iexact=value.strip())

    @staticmethod
    def global_search(queryset, _name, value):
        """
        Global search across:
        - libelle
        - facture_client.numero_facture
        - facture_client.client.raison_sociale
        """
        if not value or not value.strip():
            return queryset

        value = value.strip()

        # Detect tsquery metacharacters and skip FTS if present
        ts_meta = set(":*?&|!()<>")
        skip_fts = any(ch in ts_meta for ch in value.lower())

        search_vector = (
            SearchVector("libelle", weight="A")
            + SearchVector("facture_client__numero_facture", weight="A")
            + SearchVector("facture_client__client__raison_sociale", weight="B")
        )

        queryset_with_vector = queryset.annotate(_search=search_vector)

        if not skip_fts:
            try:
                search_query = SearchQuery(value, search_type="plain")
                fts_results = queryset_with_vector.filter(
                    _search=search_query
                ).annotate(_rank=SearchRank(F("_search"), search_query))
            except DatabaseError:
                fts_results = queryset.none().annotate(
                    _rank=Value(0.0, output_field=FloatField())
                )
        else:
            fts_results = queryset.none().annotate(
                _rank=Value(0.0, output_field=FloatField())
            )

        # Fallback to icontains search
        fallback_q = (
            Q(libelle__icontains=value)
            | Q(facture_client__numero_facture__icontains=value)
            | Q(facture_client__client__raison_sociale__icontains=value)
        )

        fallback_results = queryset.filter(fallback_q).annotate(
            _rank=Value(0.0, output_field=FloatField())
        )

        return (fts_results | fallback_results).distinct().order_by("-_rank")
