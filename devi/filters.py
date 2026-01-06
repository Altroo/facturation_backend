from core.filters import BaseDocumentFilter

from .models import Devi


class DeviFilter(BaseDocumentFilter):
    """Filter for Devi model."""

    numero_field = "numero_devis"
    req_field = "numero_demande_prix_client"
    date_field = "date_devis"

    class Meta:
        model = Devi
        fields = ["statut", "client_id", "date_after", "date_before"]
