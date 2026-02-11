import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, FloatField, F
from django.db.utils import DatabaseError

from .models import Company
from core.filters import IsEmptyAutoMixin


class CompanyFilter(IsEmptyAutoMixin, django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    date_created_after = django_filters.DateFilter(
        field_name="date_created", lookup_expr="gte", label="Date Created After"
    )
    date_created_before = django_filters.DateFilter(
        field_name="date_created", lookup_expr="lte", label="Date Created Before"
    )

    # Text lookup filters for raison_sociale
    raison_sociale__icontains = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="icontains")
    raison_sociale__istartswith = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="istartswith")
    raison_sociale__iendswith = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="iendswith")
    raison_sociale = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="exact")

    # Text lookup filters for ICE
    ICE__icontains = django_filters.CharFilter(field_name="ICE", lookup_expr="icontains")
    ICE__istartswith = django_filters.CharFilter(field_name="ICE", lookup_expr="istartswith")
    ICE__iendswith = django_filters.CharFilter(field_name="ICE", lookup_expr="iendswith")
    ICE = django_filters.CharFilter(field_name="ICE", lookup_expr="exact")

    # Text lookup filters for nom_responsable
    nom_responsable__icontains = django_filters.CharFilter(field_name="nom_responsable", lookup_expr="icontains")
    nom_responsable__istartswith = django_filters.CharFilter(field_name="nom_responsable", lookup_expr="istartswith")
    nom_responsable__iendswith = django_filters.CharFilter(field_name="nom_responsable", lookup_expr="iendswith")
    nom_responsable = django_filters.CharFilter(field_name="nom_responsable", lookup_expr="exact")

    # Text lookup filters for email
    email__icontains = django_filters.CharFilter(field_name="email", lookup_expr="icontains")
    email__istartswith = django_filters.CharFilter(field_name="email", lookup_expr="istartswith")
    email__iendswith = django_filters.CharFilter(field_name="email", lookup_expr="iendswith")
    email = django_filters.CharFilter(field_name="email", lookup_expr="exact")

    # Text lookup filters for telephone
    telephone__icontains = django_filters.CharFilter(field_name="telephone", lookup_expr="icontains")
    telephone__istartswith = django_filters.CharFilter(field_name="telephone", lookup_expr="istartswith")
    telephone__iendswith = django_filters.CharFilter(field_name="telephone", lookup_expr="iendswith")
    telephone = django_filters.CharFilter(field_name="telephone", lookup_expr="exact")

    # Dropdown filter for nbr_employe
    nbr_employe = django_filters.CharFilter(field_name="nbr_employe", lookup_expr="exact")

    class Meta:
        model = Company
        fields = [
            "date_created_after", "date_created_before",
            "raison_sociale", "raison_sociale__icontains", "raison_sociale__istartswith", "raison_sociale__iendswith",
            "ICE", "ICE__icontains", "ICE__istartswith", "ICE__iendswith",
            "nom_responsable", "nom_responsable__icontains", "nom_responsable__istartswith", "nom_responsable__iendswith",
            "email", "email__icontains", "email__istartswith", "email__iendswith",
            "telephone", "telephone__icontains", "telephone__istartswith", "telephone__iendswith",
            "nbr_employe",
        ]

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
