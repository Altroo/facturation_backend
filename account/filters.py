import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

from .models import CustomUser


class UsersFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")

    class Meta:
        model = CustomUser
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
            # Most important: first_name last_name
            SearchVector("first_name", weight="A")
            + SearchVector("last_name", weight="A")
            +
            # Important: gender and email
            SearchVector("gender", weight="B")
            + SearchVector("email", weight="B")
        )

        search_query = SearchQuery(value)

        return (
            queryset.annotate(rank=SearchRank(search_vector, search_query))
            .filter(rank__gte=0.001)  # Filter out very low relevance matches
            .order_by("-rank")
        )
