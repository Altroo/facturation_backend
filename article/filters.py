import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, F, FloatField
from django.db.utils import DatabaseError

from .models import Article


class ArticleFilter(django_filters.FilterSet):
    """FilterSet for the ``Article`` model with full‑text search support."""

    search = django_filters.CharFilter(method="global_search", label="Search")
    archived = django_filters.BooleanFilter(field_name="archived", label="Archived")
    company_id = django_filters.NumberFilter(field_name="company_id", label="Company")

    class Meta:
        model = Article
        fields = ["archived", "company_id"]

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
