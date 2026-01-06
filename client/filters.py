import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Case, When, Value, CharField, Q, F, FloatField
from django.db.utils import DatabaseError

from .models import Client


class ClientFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    archived = django_filters.BooleanFilter(field_name="archived", label="Archived")
    company_id = django_filters.NumberFilter(field_name="company_id", label="Company")
    date_created_after = django_filters.DateFilter(
        field_name="date_created", lookup_expr="gte", label="Date Created After"
    )
    date_created_before = django_filters.DateFilter(
        field_name="date_created", lookup_expr="lte", label="Date Created Before"
    )

    class Meta:
        model = Client
        fields = ["archived", "company_id", "date_created_after", "date_created_before"]

    @staticmethod
    def global_search(queryset, _name, value):
        if not value or not value.strip():
            return queryset

        value = value.strip()

        # Annotate readable client_type label
        queryset = queryset.annotate(
            client_type_display=Case(
                When(client_type="PM", then=Value("Personne morale")),
                When(client_type="PP", then=Value("Personne physique")),
                default=Value(""),
                output_field=CharField(),
            )
        )

        # build a single weighted SearchVector and annotate it once
        search_vector = (
            SearchVector("code_client", weight="A")
            + SearchVector("raison_sociale", weight="A")
            + SearchVector("nom", weight="B")
            + SearchVector("prenom", weight="B")
            + SearchVector("email", weight="B")
            + SearchVector("client_type_display", weight="B")
            + SearchVector("adresse", weight="C")
            + SearchVector("tel", weight="C")
            + SearchVector("ville__nom", weight="C")
            + SearchVector("ICE", weight="D")
            + SearchVector("registre_de_commerce", weight="D")
            + SearchVector("identifiant_fiscal", weight="D")
            + SearchVector("numero_du_compte", weight="D")
            + SearchVector("taxe_professionnelle", weight="D")
            + SearchVector("CNSS", weight="D")
            + SearchVector("fax", weight="D")
        )

        # detect tsquery metacharacters and skip FTS if present
        ts_meta = set(":*?&|!()<>")
        skip_fts = any(ch in ts_meta for ch in value)

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

        # Fallback icontains queries
        fallback_q = (
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

        fallback_results = queryset.filter(fallback_q).annotate(
            rank=Value(0.0, output_field=FloatField())
        )

        return (fts_results | fallback_results).distinct().order_by("-rank")
