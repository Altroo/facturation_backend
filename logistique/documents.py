"""Collect step-labelled attachments, including earlier uploads on closed dossiers."""

from pathlib import Path

FIELDS = {
    "proforma_fournisseur_file": ("proforma", "Proforma fournisseur"),
    "titre_importation_file": ("titre", "Titre d’importation"),
    "documents_originaux_file": ("expedition", "Expédition et documents"),
    "justificatifs_file": ("couts", "Clôture et coût réel"),
    "bon_reception_file": ("reception", "Réception des marchandises"),
}


def dossier_documents(order, request=None):
    documents = []
    seen = set()

    def add(field, name, step, label):
        if not name or (field, name) in seen:
            return
        seen.add((field, name))
        storage = order._meta.get_field("titre_importation_file").storage
        url = storage.url(name)
        documents.append(
            {
                "etape": step,
                "etape_label": label,
                "nom": Path(name).name,
                "url": request.build_absolute_uri(url) if request else url,
            }
        )

    if order.statut == "Clôture":
        for row in order.history.order_by("history_date", "history_id").values(
            *FIELDS, "statut"
        ):
            for field, (step, label) in FIELDS.items():
                if field == "justificatifs_file" and row["statut"] in {
                    "Transit",
                    "Dédouanement",
                }:
                    step, label = "transit", "Transit et dédouanement"
                elif field == "justificatifs_file" and row["statut"] == "Expédition":
                    step, label = "expedition", "Expédition et documents"
                add(field, row[field], step, label)
    for field, (step, label) in FIELDS.items():
        name = getattr(order, field).name
        if field == "justificatifs_file" and name:
            first_status = (
                order.history.filter(justificatifs_file=name)
                .order_by("history_date", "history_id")
                .values_list("statut", flat=True)
                .first()
            )
            if first_status in {"Transit", "Dédouanement"}:
                step, label = "transit", "Transit et dédouanement"
            elif first_status == "Expédition":
                step, label = "expedition", "Expédition et documents"
        add(field, name, step, label)
    for item in order.echeances_paiement.all():
        step, label = (
            ("paiement", "Avance et comptabilité")
            if item.declencheur == "advance"
            else ("solde", "Paiement et comptabilité")
        )
        add("justificatif_file", item.justificatif_file.name, step, label)
    for note in order.process_notes.all():
        add("fichier", note.fichier.name, "remarque", f"Remarque - {note.statut}")
    return documents
