import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, FloatField, F
from django.db.utils import DatabaseError

from .models import Company


class CompanyFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    date_created_after = django_filters.DateFilter(
        field_name="date_created", lookup_expr="gte", label="Date Created After"
    )
    date_created_before = django_filters.DateFilter(
        field_name="date_created", lookup_expr="lte", label="Date Created Before"
    )

    class Meta:
        model = Company
        fields = ["date_created_after", "date_created_before"]

    @staticmethod
    def global_search(queryset, _name, value):
        """
        Hybrid search: PostgreSQL full-text search + icontains fallback.
        Skip FTS if input contains tsquery metacharacters to avoid
        `tsquery` syntax errors like "Other Ave:*".
        """
        if not value:
            return queryset

        value = value.strip()
        if not value:
            return queryset

        # annotate a single weighted tsvector once
        queryset_with_vector = queryset.annotate(
            _search=(
                SearchVector("raison_sociale", weight="A")
                + SearchVector("nom_responsable", weight="B")
                + SearchVector("email", weight="B")
                + SearchVector("adresse", weight="C")
                + SearchVector("telephone", weight="C")
                + SearchVector("gsm_responsable", weight="C")
                + SearchVector("ICE", weight="D")
                + SearchVector("site_web", weight="D")
                + SearchVector("registre_de_commerce", weight="D")
                + SearchVector("identifiant_fiscal", weight="D")
                + SearchVector("numero_du_compte", weight="D")
                + SearchVector("tax_professionnelle", weight="D")
                + SearchVector("CNSS", weight="D")
                + SearchVector("fax", weight="D")
            )
        )

        # detect tsquery metacharacters and skip FTS if present
        ts_meta = set(":*?&|!()<>")
        skip_fts = any(ch in ts_meta for ch in value)

        # attempt full-text search only if safe
        if not skip_fts:
            try:
                search_query = SearchQuery(value, search_type="plain")
                fts_results = queryset_with_vector.filter(
                    _search=search_query
                ).annotate(  # uses @@ under the hood
                    rank=SearchRank(F("_search"), search_query)
                )
            except DatabaseError:
                fts_results = queryset.none().annotate(
                    rank=Value(0.0, output_field=FloatField())
                )
        else:
            fts_results = queryset.none().annotate(
                rank=Value(0.0, output_field=FloatField())
            )

        # fallback icontains, annotated with zero rank for consistent ordering
        fallback_q = (
            Q(raison_sociale__icontains=value)
            | Q(nom_responsable__icontains=value)
            | Q(email__icontains=value)
            | Q(adresse__icontains=value)
            | Q(telephone__icontains=value)
            | Q(gsm_responsable__icontains=value)
            | Q(ICE__icontains=value)
            | Q(site_web__icontains=value)
            | Q(registre_de_commerce__icontains=value)
            | Q(identifiant_fiscal__icontains=value)
            | Q(numero_du_compte__icontains=value)
            | Q(tax_professionnelle__icontains=value)
            | Q(CNSS__icontains=value)
            | Q(fax__icontains=value)
        )

        fallback_results = queryset.filter(fallback_q).annotate(
            rank=Value(0.0, output_field=FloatField())
        )

        return (fts_results | fallback_results).distinct().order_by("-rank")
