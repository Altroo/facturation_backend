from core.filters import BaseDocumentFilter

from .models import FactureClient


class FactureClientFilter(BaseDocumentFilter):
    """Filter for FactureClient model."""

    numero_field = "numero_facture"
    req_field = "numero_bon_commande_client"

    class Meta:
        model = FactureClient
        fields = ["statut", "client_id"]
