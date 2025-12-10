import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Case, When, Value, CharField, Q, F, FloatField
from django.db.utils import DatabaseError

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
        Skip FTS when value contains tsquery metacharacters (checked in lowercase).
        """
        if not value or not value.strip():
            return queryset

        value = value.strip()

        # Annotate readable gender label
        queryset = queryset.annotate(
            gender_display=Case(
                When(gender="H", then=Value("Homme")),
                When(gender="F", then=Value("Femme")),
                default=Value("Unset"),
                output_field=CharField(),
            )
        )

        # Full-text search vector (annotated once)
        search_vector = (
            SearchVector("first_name", weight="A")
            + SearchVector("last_name", weight="A")
            + SearchVector("gender_display", weight="B")
            + SearchVector("email", weight="B")
        )

        # detect tsquery metacharacters in lowercase and skip FTS if present
        ts_meta = set(":*?&|!()<>")
        skip_fts = any(ch in ts_meta for ch in value.lower())

        queryset_with_vector = queryset.annotate(_search=search_vector)

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

        # Fallback for special characters (e.g. email, gender)
        fallback_results = queryset.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
            | Q(gender_display__icontains=value)
        ).annotate(rank=Value(0.0, output_field=FloatField()))

        # Combine and deduplicate, ordering by typed rank
        return (fts_results | fallback_results).distinct().order_by("-rank")
