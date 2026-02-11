import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Case, When, Value, CharField, Q, F, FloatField
from django.db.utils import DatabaseError

from .models import Client
from core.filters import IsEmptyAutoMixin


class ClientFilter(IsEmptyAutoMixin, django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    archived = django_filters.BooleanFilter(field_name="archived", label="Archived")
    company_id = django_filters.NumberFilter(field_name="company_id", label="Company")
    date_created_after = django_filters.DateFilter(
        field_name="date_created", lookup_expr="gte", label="Date Created After"
    )
    date_created_before = django_filters.DateFilter(
        field_name="date_created", lookup_expr="lte", label="Date Created Before"
    )

    # Text field filters
    code_client__icontains = django_filters.CharFilter(field_name="code_client", lookup_expr="icontains")
    code_client__istartswith = django_filters.CharFilter(field_name="code_client", lookup_expr="istartswith")
    code_client__iendswith = django_filters.CharFilter(field_name="code_client", lookup_expr="iendswith")
    code_client = django_filters.CharFilter(field_name="code_client", lookup_expr="exact")

    raison_sociale__icontains = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="icontains")
    raison_sociale__istartswith = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="istartswith")
    raison_sociale__iendswith = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="iendswith")
    raison_sociale = django_filters.CharFilter(field_name="raison_sociale", lookup_expr="exact")

    nom__icontains = django_filters.CharFilter(field_name="nom", lookup_expr="icontains")
    nom__istartswith = django_filters.CharFilter(field_name="nom", lookup_expr="istartswith")
    nom__iendswith = django_filters.CharFilter(field_name="nom", lookup_expr="iendswith")
    nom = django_filters.CharFilter(field_name="nom", lookup_expr="exact")

    # Text lookup filters for prenom
    prenom__icontains = django_filters.CharFilter(field_name="prenom", lookup_expr="icontains")
    prenom__istartswith = django_filters.CharFilter(field_name="prenom", lookup_expr="istartswith")
    prenom__iendswith = django_filters.CharFilter(field_name="prenom", lookup_expr="iendswith")
    prenom = django_filters.CharFilter(field_name="prenom", lookup_expr="exact")

    # Dropdown filters
    client_type = django_filters.CharFilter(field_name="client_type", lookup_expr="exact")
    ville = django_filters.NumberFilter(field_name="ville_id", lookup_expr="exact")

    # Text lookup filters for ville_name (mapped to ville__nom)
    ville_name__icontains = django_filters.CharFilter(field_name="ville__nom", lookup_expr="icontains")
    ville_name__istartswith = django_filters.CharFilter(field_name="ville__nom", lookup_expr="istartswith")
    ville_name__iendswith = django_filters.CharFilter(field_name="ville__nom", lookup_expr="iendswith")
    ville_name = django_filters.CharFilter(field_name="ville__nom", lookup_expr="exact")

    class Meta:
        model = Client
        fields = [
            "archived", "company_id", "date_created_after", "date_created_before",
            "code_client", "code_client__icontains", "code_client__istartswith", "code_client__iendswith",
            "raison_sociale", "raison_sociale__icontains", "raison_sociale__istartswith", "raison_sociale__iendswith",
            "nom", "nom__icontains", "nom__istartswith", "nom__iendswith",
            "prenom", "prenom__icontains", "prenom__istartswith", "prenom__iendswith",
            "client_type", "ville",
            "ville_name", "ville_name__icontains", "ville_name__istartswith", "ville_name__iendswith",
        ]

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
