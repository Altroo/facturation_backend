import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Case, When, Value, CharField, Q, F, FloatField
from django.db.utils import DatabaseError

from .models import CustomUser
from core.filters import IsEmptyAutoMixin


class UsersFilter(IsEmptyAutoMixin, django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    date_joined_after = django_filters.DateTimeFilter(
        field_name="date_joined", lookup_expr="gte", label="Date Joined After"
    )
    date_joined_before = django_filters.DateTimeFilter(
        field_name="date_joined", lookup_expr="lte", label="Date Joined Before"
    )
    last_login_after = django_filters.DateTimeFilter(
        field_name="last_login", lookup_expr="gte", label="Last Login After"
    )
    last_login_before = django_filters.DateTimeFilter(
        field_name="last_login", lookup_expr="lte", label="Last Login Before"
    )

    # Text lookup filters for first_name
    first_name__icontains = django_filters.CharFilter(field_name="first_name", lookup_expr="icontains")
    first_name__istartswith = django_filters.CharFilter(field_name="first_name", lookup_expr="istartswith")
    first_name__iendswith = django_filters.CharFilter(field_name="first_name", lookup_expr="iendswith")
    first_name = django_filters.CharFilter(field_name="first_name", lookup_expr="exact")

    # Text lookup filters for last_name
    last_name__icontains = django_filters.CharFilter(field_name="last_name", lookup_expr="icontains")
    last_name__istartswith = django_filters.CharFilter(field_name="last_name", lookup_expr="istartswith")
    last_name__iendswith = django_filters.CharFilter(field_name="last_name", lookup_expr="iendswith")
    last_name = django_filters.CharFilter(field_name="last_name", lookup_expr="exact")

    # Text lookup filters for email
    email__icontains = django_filters.CharFilter(field_name="email", lookup_expr="icontains")
    email__istartswith = django_filters.CharFilter(field_name="email", lookup_expr="istartswith")
    email__iendswith = django_filters.CharFilter(field_name="email", lookup_expr="iendswith")
    email = django_filters.CharFilter(field_name="email", lookup_expr="exact")

    # Gender filter (maps display label to stored value)
    gender = django_filters.CharFilter(method="filter_gender", label="Gender")

    # Boolean filters
    is_staff = django_filters.BooleanFilter(field_name="is_staff", label="Is Staff")
    is_active = django_filters.BooleanFilter(field_name="is_active", label="Is Active")

    class Meta:
        model = CustomUser
        fields = [
            "date_joined_after",
            "date_joined_before",
            "last_login_after",
            "last_login_before",
            "first_name", "first_name__icontains", "first_name__istartswith", "first_name__iendswith",
            "last_name", "last_name__icontains", "last_name__istartswith", "last_name__iendswith",
            "email", "email__icontains", "email__istartswith", "email__iendswith",
            "gender", "is_staff", "is_active",
        ]

    @staticmethod
    def filter_gender(queryset, _name, value):
        """Map display labels (Homme/Femme) to stored values (H/F)."""
        if not value:
            return queryset
        mapping = {"Homme": "H", "Femme": "F", "H": "H", "F": "F"}
        mapped = mapping.get(value.strip(), value.strip())
        return queryset.filter(gender=mapped)

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
