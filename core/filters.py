import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, F, FloatField
from django.db.utils import DatabaseError


class BaseDocumentFilter(django_filters.FilterSet):
    """
    Base filter class for document models (Devi, FactureProForma, FactureClient, BonDeLivraison).

    Subclasses should set:
    - numero_field: the name of the numero field (e.g., 'numero_devis', 'numero_facture', 'numero_bon_livraison')
    - req_field: the name of the request/command field (e.g., 'numero_demande_prix_client',
    'numero_bon_commande_client')
    - date_field: the name of the date field (e.g., 'date_devis', 'date_facture', 'date_bon_livraison')
    """

    search = django_filters.CharFilter(method="global_search", label="Search")
    statut = django_filters.CharFilter(method="filter_statut", label="Status")
    client_id = django_filters.NumberFilter(field_name="client__id", label="Client ID")
    # Generic date filters that will be mapped to specific date fields by subclasses
    date_after = django_filters.DateFilter(
        method="filter_date_after", label="Date After"
    )
    date_before = django_filters.DateFilter(
        method="filter_date_before", label="Date Before"
    )

    # Subclasses should override these
    numero_field = (
        None  # e.g., 'numero_devis', 'numero_facture', 'numero_bon_livraison'
    )
    req_field = None  # e.g., 'numero_demande_prix_client', 'numero_bon_commande_client'
    date_field = None  # e.g., 'date_devis', 'date_facture', 'date_bon_livraison'

    @staticmethod
    def filter_statut(queryset, _name, value):
        if not value:
            return queryset
        return queryset.filter(statut__iexact=value.strip())

    def filter_date_after(self, queryset, _name, value):
        """Filter for dates greater than or equal to the given value."""
        if not value or not self.date_field:
            return queryset
        return queryset.filter(**{f"{self.date_field}__gte": value})

    def filter_date_before(self, queryset, _name, value):
        """Filter for dates less than or equal to the given value."""
        if not value or not self.date_field:
            return queryset
        return queryset.filter(**{f"{self.date_field}__lte": value})

    def global_search(self, queryset, _name, value):
        if not value or not value.strip():
            return queryset

        value = value.strip()

        # Validate that subclass has set the required fields
        if not self.numero_field or not self.req_field:
            raise NotImplementedError(
                "Subclass must set 'numero_field' and 'req_field' class attributes"
            )

        # detect tsquery metacharacters in lowercase and skip FTS if present
        ts_meta = set(":*?&|!()<>")
        skip_fts = any(ch in ts_meta for ch in value.lower())

        search_vector = (
            SearchVector(self.numero_field, weight="A")
            + SearchVector("client__raison_sociale", weight="A")
            + SearchVector(self.req_field, weight="B")
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

        fallback_q = (
            Q(**{f"{self.numero_field}__icontains": value})
            | Q(client__raison_sociale__icontains=value)
            | Q(**{f"{self.req_field}__icontains": value})
        )

        fallback_results = queryset.filter(fallback_q).annotate(
            _rank=Value(0.0, output_field=FloatField())
        )

        return (fts_results | fallback_results).distinct().order_by("-_rank")
