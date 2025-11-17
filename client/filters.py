import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q

from .models import Client


class ClientFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    archived = django_filters.BooleanFilter(field_name="archived", label="Archived")

    class Meta:
        model = Client
        fields = ["archived"]

    @staticmethod
    def global_search(queryset, _name, value):
        """
        Hybrid search: PostgreSQL full‑text search + icontains fallback.
        Covers all searchable fields of the `Client` model.
        """
        if not value:
            return queryset

        # Weighted search vector for the relevant fields
        search_vector = (
            SearchVector("code_client", weight="A")
            + SearchVector("raison_sociale", weight="A")
            + SearchVector("nom", weight="B")
            + SearchVector("prenom", weight="B")
            + SearchVector("email", weight="B")
            + SearchVector("adresse", weight="C")
            + SearchVector("tel", weight="C")
            + SearchVector("ICE", weight="D")
            + SearchVector("registre_de_commerce", weight="D")
            + SearchVector("identifiant_fiscal", weight="D")
            + SearchVector("numero_du_compte", weight="D")
            + SearchVector("taxe_professionnelle", weight="D")
            + SearchVector("CNSS", weight="D")
            + SearchVector("fax", weight="D")
            + SearchVector("ville__nom", weight="C")  # search by city name
        )

        # Prefix matching for full‑text search
        search_query = SearchQuery(f"{value}:*", search_type="raw")

        # Full‑text search results
        fts_results = queryset.annotate(
            rank=SearchRank(search_vector, search_query)
        ).filter(rank__gte=0.001)

        # Fallback `icontains` queries for special characters / partial matches
        fallback_results = queryset.filter(
            Q(code_client__icontains=value)
            | Q(raison_sociale__icontains=value)
            | Q(nom__icontains=value)
            | Q(prenom__icontains=value)
            | Q(email__icontains=value)
            | Q(adresse__icontains=value)
            | Q(tel__icontains=value)
            | Q(ICE__icontains=value)
            | Q(registre_de_commerce__icontains=value)
            | Q(identifiant_fiscal__icontains=value)
            | Q(numero_du_compte__icontains=value)
            | Q(taxe_professionnelle__icontains=value)
            | Q(CNSS__icontains=value)
            | Q(fax__icontains=value)
            | Q(ville__nom__icontains=value)
        )

        # Combine, deduplicate, and order by relevance rank
        return (fts_results | fallback_results).distinct().order_by("-rank")
