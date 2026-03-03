import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, F, FloatField
from django.db.utils import DatabaseError

from .models import Article
from core.filters import IsEmptyAutoMixin, CommaSeparatedIDsFilter


class ArticleFilter(IsEmptyAutoMixin, django_filters.FilterSet):
    """FilterSet for the ``Article`` model with full‑text search support."""

    search = django_filters.CharFilter(method="global_search", label="Search")
    archived = django_filters.BooleanFilter(field_name="archived", label="Archived")
    company_id = django_filters.NumberFilter(field_name="company_id", label="Company")
    date_created_after = django_filters.DateFilter(
        field_name="date_created", lookup_expr="gte", label="Date Created After"
    )
    date_created_before = django_filters.DateFilter(
        field_name="date_created", lookup_expr="lte", label="Date Created Before"
    )

    # Chip select multi-ID filters
    categorie_ids = CommaSeparatedIDsFilter(
        field_name="categorie_id", label="Categorie IDs"
    )
    emplacement_ids = CommaSeparatedIDsFilter(
        field_name="emplacement_id", label="Emplacement IDs"
    )
    unite_ids = CommaSeparatedIDsFilter(field_name="unite_id", label="Unite IDs")
    marque_ids = CommaSeparatedIDsFilter(field_name="marque_id", label="Marque IDs")

    # Text field filters
    reference__icontains = django_filters.CharFilter(
        field_name="reference", lookup_expr="icontains"
    )
    reference__istartswith = django_filters.CharFilter(
        field_name="reference", lookup_expr="istartswith"
    )
    reference__iendswith = django_filters.CharFilter(
        field_name="reference", lookup_expr="iendswith"
    )
    reference = django_filters.CharFilter(field_name="reference", lookup_expr="exact")

    designation__icontains = django_filters.CharFilter(
        field_name="designation", lookup_expr="icontains"
    )
    designation__istartswith = django_filters.CharFilter(
        field_name="designation", lookup_expr="istartswith"
    )
    designation__iendswith = django_filters.CharFilter(
        field_name="designation", lookup_expr="iendswith"
    )
    designation = django_filters.CharFilter(
        field_name="designation", lookup_expr="exact"
    )

    # Dropdown filters
    type_article = django_filters.CharFilter(
        field_name="type_article", lookup_expr="exact"
    )

    # Numeric field filters for prix_achat
    prix_achat = django_filters.NumberFilter(
        field_name="prix_achat", lookup_expr="exact"
    )
    prix_achat__gt = django_filters.NumberFilter(
        field_name="prix_achat", lookup_expr="gt"
    )
    prix_achat__gte = django_filters.NumberFilter(
        field_name="prix_achat", lookup_expr="gte"
    )
    prix_achat__lt = django_filters.NumberFilter(
        field_name="prix_achat", lookup_expr="lt"
    )
    prix_achat__lte = django_filters.NumberFilter(
        field_name="prix_achat", lookup_expr="lte"
    )
    prix_achat__ne = django_filters.NumberFilter(field_name="prix_achat", exclude=True)

    # Numeric field filters for prix_vente
    prix_vente = django_filters.NumberFilter(
        field_name="prix_vente", lookup_expr="exact"
    )
    prix_vente__gt = django_filters.NumberFilter(
        field_name="prix_vente", lookup_expr="gt"
    )
    prix_vente__gte = django_filters.NumberFilter(
        field_name="prix_vente", lookup_expr="gte"
    )
    prix_vente__lt = django_filters.NumberFilter(
        field_name="prix_vente", lookup_expr="lt"
    )
    prix_vente__lte = django_filters.NumberFilter(
        field_name="prix_vente", lookup_expr="lte"
    )
    prix_vente__ne = django_filters.NumberFilter(field_name="prix_vente", exclude=True)

    class Meta:
        model = Article
        fields = [
            "archived",
            "company_id",
            "date_created_after",
            "date_created_before",
            "reference",
            "reference__icontains",
            "reference__istartswith",
            "reference__iendswith",
            "designation",
            "designation__icontains",
            "designation__istartswith",
            "designation__iendswith",
            "type_article",
            "prix_achat",
            "prix_achat__gt",
            "prix_achat__gte",
            "prix_achat__lt",
            "prix_achat__lte",
            "prix_achat__ne",
            "prix_vente",
            "prix_vente__gt",
            "prix_vente__gte",
            "prix_vente__lt",
            "prix_vente__lte",
            "prix_vente__ne",
        ]

    @staticmethod
    def global_search(queryset, _name, value):
        """Hybrid PostgreSQL full‑text search + icontains fallback."""
        if not value or not value.strip():
            return queryset

        value = value.strip()

        # Build a weighted search vector covering the most relevant fields.
        search_vector = (
            SearchVector("reference", weight="A")
            + SearchVector("designation", weight="A")
            + SearchVector("marque__nom", weight="B")
            + SearchVector("categorie__nom", weight="B")
            + SearchVector("unite__nom", weight="C")
            + SearchVector("emplacement__nom", weight="C")
        )

        # detect tsquery metacharacters and skip FTS if present
        ts_meta = set(":*?&|!()<>")
        skip_fts = any(ch in ts_meta for ch in value)

        # Annotate the search vector once
        queryset_with_vector = queryset.annotate(_search=search_vector)

        if not skip_fts:
            try:
                search_query = SearchQuery(value, search_type="plain")
                fts_results = queryset_with_vector.filter(
                    _search=search_query
                ).annotate(  # uses @@ under the hood
                    _rank=SearchRank(F("_search"), search_query)
                )
            except DatabaseError:
                fts_results = queryset.none().annotate(
                    _rank=Value(0.0, output_field=FloatField())
                )
        else:
            fts_results = queryset.none().annotate(
                _rank=Value(0.0, output_field=FloatField())
            )

        # Fallback icontains queries for fields not covered by full‑text search
        fallback_q = (
            Q(reference__icontains=value)
            | Q(designation__icontains=value)
            | Q(marque__nom__icontains=value)
            | Q(categorie__nom__icontains=value)
            | Q(unite__nom__icontains=value)
            | Q(emplacement__nom__icontains=value)
        )

        fallback_results = queryset.filter(fallback_q).annotate(
            _rank=Value(0.0, output_field=FloatField())
        )

        # Union FTS and fallback, ensure typed _rank for stable ordering
        return (fts_results | fallback_results).distinct().order_by("-_rank")
