from core.filters import BaseDocumentFilter

from .models import BonDeLivraison


class BonDeLivraisonFilter(BaseDocumentFilter):
    """Filter for BonDeLivraison model."""

    numero_field = "numero_bon_livraison"
    req_field = "numero_bon_commande_client"
    date_field = "date_bon_livraison"

    class Meta:
        model = BonDeLivraison
        fields = ["statut", "client_id", "date_after", "date_before"]
