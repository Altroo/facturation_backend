from core.filters import BaseDocumentFilter

from .models import BonDeLivraison


class BonDeLivraisonFilter(BaseDocumentFilter):
    """Filter for BonDeLivraison model."""

    numero_field = "numero_bon_livraison"
    req_field = "numero_bon_commande_client"

    class Meta:
        model = BonDeLivraison
        fields = ["statut", "client_id"]
