from core.filters import BaseDocumentFilter

from .models import FactureProForma


class FactureProFormaFilter(BaseDocumentFilter):
    """Filter for FactureProForma model."""

    numero_field = "numero_facture"
    req_field = "numero_bon_commande_client"
    date_field = "date_facture"

    class Meta:
        model = FactureProForma
        fields = ["statut", "client_id", "date_after", "date_before"]
