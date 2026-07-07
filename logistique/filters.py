import django_filters
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.filters import CommaSeparatedIDsFilter, IsEmptyAutoMixin

from .models import LogisticsOrder


class LogisticsOrderFilter(IsEmptyAutoMixin, django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label=_("Search"))
    statut = django_filters.CharFilter(method="filter_statut")
    statut_paiement = django_filters.CharFilter(method="filter_statut_paiement")
    statut_titre_importation = django_filters.CharFilter(
        method="filter_statut_titre_importation"
    )
    marque_id = django_filters.NumberFilter(field_name="marque_id")
    marque_ids = CommaSeparatedIDsFilter(field_name="marque_id")
    date_prevue_after = django_filters.DateFilter(
        field_name="date_prevue", lookup_expr="gte"
    )
    date_prevue_before = django_filters.DateFilter(
        field_name="date_prevue", lookup_expr="lte"
    )
    date_reelle_after = django_filters.DateFilter(
        field_name="date_reelle", lookup_expr="gte"
    )
    date_reelle_before = django_filters.DateFilter(
        field_name="date_reelle", lookup_expr="lte"
    )

    numero_commande = django_filters.CharFilter(
        field_name="numero_commande", lookup_expr="exact"
    )
    numero_commande__icontains = django_filters.CharFilter(
        field_name="numero_commande", lookup_expr="icontains"
    )
    fournisseur = django_filters.CharFilter(method="filter_fournisseur")
    fournisseur__icontains = django_filters.CharFilter(
        field_name="fournisseur", lookup_expr="icontains"
    )
    clients_display__icontains = django_filters.CharFilter(method="filter_client_name")
    marque_name__icontains = django_filters.CharFilter(
        field_name="marque__nom", lookup_expr="icontains"
    )

    cout_total = django_filters.NumberFilter(field_name="cout_total", lookup_expr="exact")
    cout_total__gt = django_filters.NumberFilter(
        field_name="cout_total", lookup_expr="gt"
    )
    cout_total__gte = django_filters.NumberFilter(
        field_name="cout_total", lookup_expr="gte"
    )
    cout_total__lt = django_filters.NumberFilter(
        field_name="cout_total", lookup_expr="lt"
    )
    cout_total__lte = django_filters.NumberFilter(
        field_name="cout_total", lookup_expr="lte"
    )
    cout_total__ne = django_filters.NumberFilter(
        field_name="cout_total", exclude=True
    )

    class Meta:
        model = LogisticsOrder
        fields = [
            "statut",
            "statut_paiement",
            "statut_titre_importation",
            "marque_id",
            "date_prevue_after",
            "date_prevue_before",
            "date_reelle_after",
            "date_reelle_before",
            "numero_commande",
            "numero_commande__icontains",
            "fournisseur",
            "fournisseur__icontains",
            "marque_name__icontains",
            "cout_total",
            "cout_total__gt",
            "cout_total__gte",
            "cout_total__lt",
            "cout_total__lte",
            "cout_total__ne",
        ]

    @staticmethod
    def filter_statut(queryset, _name, value):
        if not value:
            return queryset
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            return queryset
        if len(values) == 1:
            return queryset.filter(statut__iexact=values[0])
        return queryset.filter(statut__in=values)

    @staticmethod
    def filter_statut_paiement(queryset, _name, value):
        if not value:
            return queryset
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            return queryset
        if len(values) == 1:
            return queryset.filter(statut_paiement__iexact=values[0])
        return queryset.filter(statut_paiement__in=values)

    @staticmethod
    def filter_statut_titre_importation(queryset, _name, value):
        if not value:
            return queryset
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            return queryset
        if len(values) == 1:
            return queryset.filter(statut_titre_importation__iexact=values[0])
        return queryset.filter(statut_titre_importation__in=values)

    @staticmethod
    def filter_fournisseur(queryset, _name, value):
        if not value:
            return queryset
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            return queryset
        if len(values) == 1:
            return queryset.filter(fournisseur__iexact=values[0])
        return queryset.filter(fournisseur__in=values)

    @staticmethod
    def filter_client_name(queryset, _name, value):
        if not value:
            return queryset
        value = value.strip()
        return queryset.filter(
            Q(lignes__client__raison_sociale__icontains=value)
            | Q(lignes__client__nom__icontains=value)
            | Q(lignes__client__prenom__icontains=value)
        ).distinct()

    @staticmethod
    def global_search(queryset, _name, value):
        if not value or not value.strip():
            return queryset
        value = value.strip()
        return queryset.filter(
            Q(numero_commande__icontains=value)
            | Q(fournisseur__icontains=value)
            | Q(marque__nom__icontains=value)
            | Q(statut__icontains=value)
            | Q(statut_paiement__icontains=value)
            | Q(lignes__client__raison_sociale__icontains=value)
            | Q(lignes__client__nom__icontains=value)
            | Q(lignes__client__prenom__icontains=value)
            | Q(proformas__numero_facture__icontains=value)
        ).distinct()
