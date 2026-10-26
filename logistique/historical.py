"""Step boundaries for dossiers created from customer proformas."""

STEPS = (
    ("dossier", "Commande & lancement"),
    ("proforma", "Proforma & conformité"),
    ("paiement", "Banque & paiement"),
    ("production", "Préparation fournisseur"),
    ("expedition", "Expédition & documents"),
    ("transit", "Transit & douane"),
    ("reception", "Réception & livraison"),
    ("couts", "Clôture & coût réel"),
)

EDIT_FIELDS = {
    "dossier": {"description", "responsable", "marques", "justificatifs_file"},
    "proforma": {"origine_marchandise", "nature_marchandise", "poids_net", "poids_brut"},
    "paiement": {"numero_domiciliation", "banque", "montant_titre_importation", "devise_titre_importation", "date_titre_importation", "methode_paiement", "avance_pourcentage", "titre_importation_file"},
    "production": {"date_prevue"},
    "expedition": {"transport", "documents_originaux_requis", "statut_documents_originaux", "documents_originaux_file"},
    "transit": {"frais_transit", "frais_douane", "tva"},
    "reception": {"date_reelle", "livraison_locale"},
    "couts": {"cout_transport", "frais_transit", "frais_douane", "tva", "livraison_locale", "autres_frais", "justificatifs_file"},
}


def historical_steps(order):
    if not order.is_launch_step_complete:
        index = 0
    elif not order.is_proforma_step_complete:
        index = 1
    elif not order.is_payment_step_complete:
        index = 2
    else:
        index = {"Production": 3, "Expédition": 4, "Transit": 5, "Dédouanement": 5,
                 "Réception locale": 6, "Livraison client": 7, "Clôture": 7}.get(order.statut, 2)
    steps = [{"key": key, "label": label, "completed": position < index or order.statut == "Clôture",
              "accessible": position <= index}
             for position, (key, label) in enumerate(STEPS)]
    return steps, steps[index]["key"]


def authorize_historical_edit(order, request):
    from rest_framework.exceptions import ValidationError
    from .corrections import authorize_step
    _, current = historical_steps(order)
    selected = request.data.get("etape", current)
    approval = authorize_step(order, request, selected)
    allowed = EDIT_FIELDS.get(selected, set()) | {"etape", "correction_id"}
    if selected == current:
        allowed |= {"statut"}
    if set(request.data) - allowed:
        raise ValidationError({"etape": "Modifiez uniquement les champs de l’étape sélectionnée."})
    target = request.data.get("statut", order.statut)
    if target != order.statut:
        targets = {"paiement": {"Production"} if order.is_payment_step_complete else set(),
                   "production": {"Expédition"}, "expedition": {"Transit"},
                   "transit": {"Dédouanement", "Réception locale"},
                   "reception": {"Livraison client"}, "couts": {"Clôture"}}
        if target not in targets.get(current, set()):
            raise ValidationError({"statut": "Terminez l’étape en cours avant de poursuivre."})
    if approval and selected == "paiement":
        # A reference correction must not change the validated accounting schedule.
        for field in ("montant_titre_importation", "devise_titre_importation", "methode_paiement", "avance_pourcentage"):
            if field in request.data and str(request.data[field]) != str(getattr(order, field)):
                raise ValidationError({field: "Cette valeur reste liée au paiement comptabilisé."})
    return approval
