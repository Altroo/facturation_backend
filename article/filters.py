import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value
from django.db.models.functions import Coalesce

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

        # Build a weighted search vector covering the most relevant fields.
        search_vector = (
            SearchVector("reference", weight="A")
            + SearchVector("designation", weight="A")
            + SearchVector("marque__nom", weight="B")
            + SearchVector("categorie__nom", weight="B")
            + SearchVector("unite__nom", weight="C")
            + SearchVector("emplacement__nom", weight="C")
        )

        # Plain‑text query (prefix matching is handled by the fallback).
        search_query = SearchQuery(value.strip(), search_type="plain")

        # Fallback icontains queries for fields not covered by full‑text search
        # or when the search vector yields no rank.
        fallback_q = (
            Q(reference__icontains=value)
            | Q(designation__icontains=value)
            | Q(marque__nom__icontains=value)
            | Q(categorie__nom__icontains=value)
            | Q(unite__nom__icontains=value)
            | Q(emplacement__nom__icontains=value)
        )

        # Annotate rank (0.0 when only fallback matches) and filter.
        return (
            queryset.annotate(
                _rank=Coalesce(SearchRank(search_vector, search_query), Value(0.0))
            )
            .filter(Q(_rank__gte=0.001) | fallback_q)
            .distinct()
            .order_by("-_rank")
        )
