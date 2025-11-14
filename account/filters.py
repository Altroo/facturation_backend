import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Case, When, Value, CharField, Q

from .models import CustomUser


class UsersFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")

    class Meta:
        model = CustomUser
        fields = []

    @staticmethod
    def global_search(queryset, _name, value):
        """
        Hybrid search: PostgreSQL full-text search + icontains fallback for special characters.
        """
        if not value:
            return queryset

        # Annotate readable gender label
        queryset = queryset.annotate(
            gender_display=Case(
                When(gender="H", then=Value("Homme")),
                When(gender="F", then=Value("Femme")),
                default=Value("Unset"),
                output_field=CharField(),
            )
        )

        # Full-text search vector
        search_vector = (
            SearchVector("first_name", weight="A")
            + SearchVector("last_name", weight="A")
            + SearchVector("gender_display", weight="B")
            + SearchVector("email", weight="B")
        )

        search_query = SearchQuery(f"{value}:*", search_type="raw")

        # Full-text search
        fts_results = queryset.annotate(
            rank=SearchRank(search_vector, search_query)
        ).filter(rank__gte=0.001)

        # Fallback for special characters (e.g. email, gender)
        fallback_results = queryset.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
            | Q(gender_display__icontains=value)
        )

        # Combine and deduplicate
        return (fts_results | fallback_results).distinct().order_by("-rank")
