from core.filters import BaseDocumentFilter

from .models import BonDeLivraison


class BonDeLivraisonFilter(BaseDocumentFilter):
    """Filter for BonDeLivraison model."""

    numero_field = "numero_bon_livraison"
    req_field = "numero_bon_commande_client"
    date_field = "date_bon_livraison"

    class Meta:
        model = BonDeLivraison
        fields = [
            "statut", "client_id", "date_after", "date_before",
            "total_ttc_apres_remise", "total_ttc_apres_remise__gt", "total_ttc_apres_remise__gte",
            "total_ttc_apres_remise__lt", "total_ttc_apres_remise__lte", "total_ttc_apres_remise__ne",
            "lignes_count", "lignes_count__gt", "lignes_count__gte",
            "lignes_count__lt", "lignes_count__lte", "lignes_count__ne",
            "client_name", "client_name__icontains", "client_name__istartswith", "client_name__iendswith",
        ]
