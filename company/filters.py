import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

from .models import Company


class CompanyFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")

    class Meta:
        model = Company
        fields = []

    @staticmethod
    def global_search(queryset, _name, value):
        """
        PostgreSQL full-text search across multiple Company fields.
        Uses weighted search vectors for better relevance ranking.
        """
        if not value:
            return queryset

        # Define search vectors with weights (A=highest, D=lowest)
        search_vector = (
            # Most important: company name
            SearchVector("raison_sociale", weight="A")
            +
            # Important: contact person and email
            SearchVector("nom_responsable", weight="B")
            + SearchVector("email", weight="B")
            +
            # Moderately important: address and contact details
            SearchVector("adresse", weight="C")
            + SearchVector("telephone", weight="C")
            + SearchVector("gsm_responsable", weight="C")
            +
            # Less important: administrative identifiers and other fields
            SearchVector("ICE", weight="D")
            + SearchVector("site_web", weight="D")
            + SearchVector("registre_de_commerce", weight="D")
            + SearchVector("identifiant_fiscal", weight="D")
            + SearchVector("numero_du_compte", weight="D")
            + SearchVector("tax_professionnelle", weight="D")
            + SearchVector("CNSS", weight="D")
            + SearchVector("fax", weight="D")
        )

        search_query = SearchQuery(value)

        return (
            queryset.annotate(rank=SearchRank(search_vector, search_query))
            .filter(rank__gte=0.001)  # Filter out very low relevance matches
            .order_by("-rank")
        )
