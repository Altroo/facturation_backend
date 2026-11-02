"""Dossier queries shared by logistics endpoints and business services."""

from django.http import Http404
from django.utils.translation import gettext_lazy as _

from .models import LogisticsOrder


def get_order(pk, *, for_update=False):
    try:
        queryset = LogisticsOrder.objects
        if for_update:
            queryset = queryset.select_for_update(of=("self",))
        return (
            queryset.select_related(
                "company",
                "marque",
                "responsable",
                "created_by_user",
                "demande_paiement_envoyee_par",
                "proforma_demandee_par",
                "proforma_controlee_par",
                "proforma_validee_par",
                "paiement_valide_par",
                "paiement_assigne_a",
            )
            .prefetch_related(
                "marques",
                "proformas",
                "proformas__source_devis",
                "lignes",
                "lignes__client",
                "lignes__article",
                "lignes__expected_emplacement",
                "events",
                "change_requests__demandeur",
                "change_requests__files",
                "process_notes",
                "process_notes__user",
                "echeances_paiement",
                "echeances_paiement__execution_enregistree_par",
                "echeances_paiement__paiement_valide_par",
                "echeances_paiement__reception_confirmee_par",
            )
            .get(pk=pk)
        )
    except LogisticsOrder.DoesNotExist:
        raise Http404(_("Aucun dossier logistique ne correspond à la requête."))
