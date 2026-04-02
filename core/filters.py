import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, F, FloatField, Count
from django.db.utils import DatabaseError
from django.utils.translation import gettext_lazy as _


class CommaSeparatedIDsFilter(django_filters.CharFilter):
    """Accept a comma-separated list of integer IDs and filter with ``__in``."""

    def filter(self, qs, value):
        if not value:
            return qs
        try:
            ids = [int(v.strip()) for v in value.split(",") if v.strip()]
        except (ValueError, TypeError):
            return qs
        if not ids:
            return qs
        return qs.filter(**{f"{self.field_name}__in": ids})


class IsEmptyFilter(django_filters.BooleanFilter):
    """Filter that checks both NULL and empty string for a field."""

    def filter(self, qs, value):
        if value is None:
            return qs
        empty_q = Q(**{f"{self.field_name}__isnull": True}) | Q(
            **{f"{self.field_name}__exact": ""}
        )
        return qs.filter(empty_q) if value else qs.exclude(empty_q)


def add_is_empty_filters(filterset):
    """Add ``<name>__isempty`` BooleanFilter siblings for every base
    CharFilter (those whose param name contains no ``__``) that does
    not use a custom method.  For NumberFilter base fields, adds an
    ``isnull`` lookup instead (numbers have no empty-string concept)."""
    for name, filt in list(filterset.filters.items()):
        if "__" in name or filt.method is not None or not filt.field_name:
            continue
        isempty_name = f"{name}__isempty"
        if isempty_name in filterset.filters:
            continue
        if isinstance(filt, django_filters.CharFilter):
            filterset.filters[isempty_name] = IsEmptyFilter(field_name=filt.field_name)
        elif isinstance(filt, django_filters.NumberFilter):
            filterset.filters[isempty_name] = django_filters.BooleanFilter(
                field_name=filt.field_name, lookup_expr="isnull"
            )


class IsEmptyAutoMixin:
    """Mixin for FilterSet subclasses that auto-generates ``__isempty``
    filters for every base CharFilter / NumberFilter field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_is_empty_filters(self)


class BaseDocumentFilter(django_filters.FilterSet):
    """
    Base filter class for document models (Devi, FactureProForma, FactureClient, BonDeLivraison).

    Subclasses should set:
    - numero_field: the name of the numero field (e.g., 'numero_devis', 'numero_facture', 'numero_bon_livraison')
    - req_field: the name of the request/command field (e.g., 'numero_demande_prix_client',
    'numero_bon_commande_client')
    - date_field: the name of the date field (e.g., 'date_devis', 'date_facture', 'date_bon_livraison')
    """

    search = django_filters.CharFilter(method="global_search", label=_("Search"))
    statut = django_filters.CharFilter(method="filter_statut", label=_("Status"))
    client_id = django_filters.NumberFilter(field_name="client__id", label=_("Client ID"))
    mode_paiement_ids = CommaSeparatedIDsFilter(
        field_name="mode_paiement_id", label=_("Mode de paiement IDs")
    )
    # Generic date filters that will be mapped to specific date fields by subclasses
    date_after = django_filters.DateFilter(
        method="filter_date_after", label=_("Date After")
    )
    date_before = django_filters.DateFilter(
        method="filter_date_before", label=_("Date Before")
    )

    # Numeric filters for common document fields
    total_ttc_apres_remise = django_filters.NumberFilter(
        field_name="total_ttc_apres_remise", lookup_expr="exact"
    )
    total_ttc_apres_remise__gt = django_filters.NumberFilter(
        field_name="total_ttc_apres_remise", lookup_expr="gt"
    )
    total_ttc_apres_remise__gte = django_filters.NumberFilter(
        field_name="total_ttc_apres_remise", lookup_expr="gte"
    )
    total_ttc_apres_remise__lt = django_filters.NumberFilter(
        field_name="total_ttc_apres_remise", lookup_expr="lt"
    )
    total_ttc_apres_remise__lte = django_filters.NumberFilter(
        field_name="total_ttc_apres_remise", lookup_expr="lte"
    )
    total_ttc_apres_remise__ne = django_filters.NumberFilter(
        field_name="total_ttc_apres_remise", exclude=True
    )

    # Numeric filters for lignes_count (annotated Count of related lignes)
    lignes_count = django_filters.NumberFilter(
        method="filter_lignes_count_exact", label=_("Lignes Count")
    )
    lignes_count__gt = django_filters.NumberFilter(
        method="filter_lignes_count_gt", label=_("Lignes Count (>)")
    )
    lignes_count__gte = django_filters.NumberFilter(
        method="filter_lignes_count_gte", label=_("Lignes Count (>=)")
    )
    lignes_count__lt = django_filters.NumberFilter(
        method="filter_lignes_count_lt", label=_("Lignes Count (<)")
    )
    lignes_count__lte = django_filters.NumberFilter(
        method="filter_lignes_count_lte", label=_("Lignes Count (<=)")
    )
    lignes_count__ne = django_filters.NumberFilter(
        method="filter_lignes_count_ne", label=_("Lignes Count (!=)")
    )

    # Text lookup filters for client_name (mapped to client__raison_sociale)
    client_name__icontains = django_filters.CharFilter(
        field_name="client__raison_sociale", lookup_expr="icontains"
    )
    client_name__istartswith = django_filters.CharFilter(
        field_name="client__raison_sociale", lookup_expr="istartswith"
    )
    client_name__iendswith = django_filters.CharFilter(
        field_name="client__raison_sociale", lookup_expr="iendswith"
    )
    client_name = django_filters.CharFilter(
        field_name="client__raison_sociale", lookup_expr="exact"
    )

    # Subclasses should override these
    numero_field = (
        None  # e.g., 'numero_devis', 'numero_facture', 'numero_bon_livraison'
    )
    req_field = None  # e.g., 'numero_demande_prix_client', 'numero_bon_commande_client'
    date_field = None  # e.g., 'date_devis', 'date_facture', 'date_bon_livraison'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically add text-lookup filters for numero_field and req_field
        if self.numero_field:
            nf = self.numero_field
            for suffix, lookup in [
                ("__icontains", "icontains"),
                ("__istartswith", "istartswith"),
                ("__iendswith", "iendswith"),
            ]:
                name = nf + suffix
                if name not in self.filters:
                    self.filters[name] = django_filters.CharFilter(
                        field_name=nf, lookup_expr=lookup
                    )
            # exact filter (without suffix)
            if nf not in self.filters:
                self.filters[nf] = django_filters.CharFilter(
                    field_name=nf, lookup_expr="exact"
                )
        if self.req_field:
            rf = self.req_field
            for suffix, lookup in [
                ("__icontains", "icontains"),
                ("__istartswith", "istartswith"),
                ("__iendswith", "iendswith"),
            ]:
                name = rf + suffix
                if name not in self.filters:
                    self.filters[name] = django_filters.CharFilter(
                        field_name=rf, lookup_expr=lookup
                    )
            if rf not in self.filters:
                self.filters[rf] = django_filters.CharFilter(
                    field_name=rf, lookup_expr="exact"
                )
        # Auto-generate __isempty filters for all base CharFilter / NumberFilter fields
        add_is_empty_filters(self)

    @staticmethod
    def _annotate_lignes_count(queryset):
        """Annotate queryset with lignes_count if not already present."""
        if not queryset.query.annotations.get("lignes_count"):
            queryset = queryset.annotate(lignes_count=Count("lignes"))
        return queryset

    @classmethod
    def filter_lignes_count_exact(cls, queryset, _name, value):
        if value is None:
            return queryset
        return cls._annotate_lignes_count(queryset).filter(lignes_count=value)

    @classmethod
    def filter_lignes_count_gt(cls, queryset, _name, value):
        if value is None:
            return queryset
        return cls._annotate_lignes_count(queryset).filter(lignes_count__gt=value)

    @classmethod
    def filter_lignes_count_gte(cls, queryset, _name, value):
        if value is None:
            return queryset
        return cls._annotate_lignes_count(queryset).filter(lignes_count__gte=value)

    @classmethod
    def filter_lignes_count_lt(cls, queryset, _name, value):
        if value is None:
            return queryset
        return cls._annotate_lignes_count(queryset).filter(lignes_count__lt=value)

    @classmethod
    def filter_lignes_count_lte(cls, queryset, _name, value):
        if value is None:
            return queryset
        return cls._annotate_lignes_count(queryset).filter(lignes_count__lte=value)

    @classmethod
    def filter_lignes_count_ne(cls, queryset, _name, value):
        if value is None:
            return queryset
        return cls._annotate_lignes_count(queryset).exclude(lignes_count=value)

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
