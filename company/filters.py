import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q

from .models import Company


class CompanyFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")

    class Meta:
        model = Company
        fields = []

    @staticmethod
    def global_search(queryset, _name, value):
        """
        Hybrid search: PostgreSQL full-text search + icontains fallback for special characters.
        Supports partial matching and relevance ranking.
        """
        if not value:
            return queryset

        # Define weighted search vector
        search_vector = (
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

        # Use prefix matching for full-text search
        search_query = SearchQuery(f"{value}:*", search_type="raw")

        # Full-text search results
        fts_results = queryset.annotate(
            rank=SearchRank(search_vector, search_query)
        ).filter(rank__gte=0.001)

        # Fallback for special characters and partial matches
        fallback_results = queryset.filter(
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

        # Combine and deduplicate
        return (fts_results | fallback_results).distinct().order_by("-rank")
