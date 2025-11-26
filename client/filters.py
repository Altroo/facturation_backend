import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Case, When, Value, CharField, Q

from .models import Client


class ClientFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    archived = django_filters.BooleanFilter(field_name="archived", label="Archived")
    company_id = django_filters.NumberFilter(field_name="company_id", label="Company")

    class Meta:
        model = Client
        fields = ["archived", "company_id"]

    @staticmethod
    def global_search(queryset, _name, value):
        """
        Hybrid search: PostgreSQL full‑text search + icontains fallback.
        Covers all searchable fields of the `Client` model.
        """
        if not value or not value.strip():
            return queryset

        # Annotate readable client_type label
        queryset = queryset.annotate(
            client_type_display=Case(
                When(client_type="PM", then=Value("Personne morale")),
                When(client_type="PP", then=Value("Personne physique")),
                default=Value(""),
                output_field=CharField(),
            )
        )

        # Weighted search vector for relevant fields
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

        # Prefix matching for full‑text search
        search_query = SearchQuery(value.strip(), search_type="plain")

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

        # Annotate rank for all results (0.0 for fallback-only matches)
        from django.db.models.functions import Coalesce

        combined_results = (
            queryset.annotate(
                _rank=Coalesce(SearchRank(search_vector, search_query), Value(0.0))
            )
            .filter(Q(_rank__gte=0.001) | fallback_q)
            .distinct()
            .order_by("-_rank")
        )

        return combined_results
