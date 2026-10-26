"""Proposed step edits remain separate from the dossier until accepted."""
import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

from django.core.files import File
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import LogisticsChangeRequestFile

FILE_FIELDS = {
    "proforma_fournisseur_file", "titre_importation_file", "documents_originaux_file", "justificatifs_file",
}
ACTIONS = {"dossier", "proforma", "titre", "progression", "corriger_paiement", "corriger_reception", "historical"}
CONTROL_FIELDS = {"action", "etape", "correction_id"}


def _json(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def state_for(order, data):
    """Compare only submitted values so another step can progress while review is pending."""
    result = {}
    fields = {field.name: field for field in order._meta.fields}
    for key in data:
        if key in CONTROL_FIELDS:
            continue
        if key in fields:
            value = getattr(order, fields[key].attname)
            result[key] = value.name if hasattr(value, "name") else value
    if "marques" in data:
        result["marques"] = list(order.marques.order_by("pk").values_list("pk", flat=True))
    if "lignes" in data:
        result["lignes"] = list(order.lignes.order_by("pk").values(
            "article_id", "quantity", "prix_achat", "expected_emplacement_id"))
    if data.get("action") == "corriger_paiement":
        item = order.echeances_paiement.filter(pk=data.get("echeance_id")).first()
        if item:
            result["paiement"] = {"id": item.pk, "reference": item.reference_bancaire,
                "commentaire": item.commentaire, "montant": item.montant_paye, "devise": item.devise}
    if data.get("action") == "corriger_reception":
        item = order.stock_receipts.filter(pk=data.get("reception_id"), company_id=order.company_id).first()
        if item:
            result["reception"] = {"id": item.pk, "reference": item.reference, "note": item.note}
    return _json(result)


def display_values(order, data):
    from .purchase_views import _business_snapshot
    values = _business_snapshot(order, include_lines="lignes" in data)
    if not order.is_supplier_purchase:
        values.update(description=order.description or "", marques=", ".join(order.marques.order_by("pk").values_list("nom", flat=True)),
            methode_paiement=order.methode_paiement or "", avance_pourcentage=str(order.avance_pourcentage or ""))
    if data.get("action") == "corriger_paiement":
        item = order.echeances_paiement.filter(pk=data.get("echeance_id")).first()
        if item:
            values.update(reference_paiement=item.reference_bancaire, commentaire_paiement=item.commentaire)
    if data.get("action") == "corriger_reception":
        item = order.stock_receipts.filter(pk=data.get("reception_id"), company_id=order.company_id).first()
        if item:
            values.update(reference=item.reference, note=item.note)
    return values


def prepare_proposal(order, item, request, apply_action):
    """Run the real update in a rolled-back savepoint, then retain its proposed differences."""
    from .corrections import action_step
    from .purchase_views import _BUSINESS_FIELDS
    from .serializers import validate_logistics_document
    raw = request.data.get("modifications")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raise ValidationError({"modifications": "La proposition est illisible."})
    data = serializers.JSONField().run_validation(raw)
    if not isinstance(data, dict) or data.get("action") not in ACTIONS:
        raise ValidationError({"modifications": "Renseignez les modifications de l’étape."})
    if set(data) & {"correction_id", "modifications", "demande_id"}:
        raise ValidationError({"modifications": "La proposition contient des informations non autorisées."})
    data["etape"] = item.etape
    selected = item.etape if data["action"] == "historical" and not order.is_supplier_purchase else action_step(order, data)
    if selected != item.etape:
        raise ValidationError({"etape": "La proposition doit concerner uniquement l’étape sélectionnée."})
    files = dict(request.FILES.items())
    if set(files) - FILE_FIELDS:
        raise ValidationError({"fichiers": "Ce document ne peut pas être joint à cette correction."})
    for uploaded in files.values():
        validate_logistics_document(uploaded)
    initial_data = {**data, **{field: None for field in files}}
    item.original_data = state_for(order, initial_data)
    before = display_values(order, data)
    original_paths = {field: getattr(order, field).name for field in files}
    # Stream a copy during preview; storage must not move the temporary upload.
    preview_files = {field: File(uploaded.file, name=uploaded.name) for field, uploaded in files.items()}
    preview = SimpleNamespace(user=request.user, data={**data, **preview_files}, FILES=preview_files, method="POST")
    preview_order = order
    try:
        with transaction.atomic():
            preview_order = apply_action(order, preview, item)
            after = display_values(preview_order, data)
            for field in files:
                if getattr(preview_order, field).name == original_paths[field]:
                    raise ValidationError({field: "Ce document ne peut pas être modifié dans cette étape."})
            labels = {**_BUSINESS_FIELDS, "lignes": "Articles de la proforma fournisseur",
                "reference_paiement": "Référence du paiement", "commentaire_paiement": "Commentaire du paiement",
                "reference": "Référence de réception", "note": "Remarque de réception",
                "description": "Remarque du dossier", "marques": "Marques", "marque": "Marque",
                "methode_paiement": "Méthode de paiement", "avance_pourcentage": "Avance (%)"}
            item.changes = [{"field": field, "label": labels.get(field, field), "before": before[field],
                "after": files[field].name if field in files else new_value}
                for field, new_value in after.items() if before.get(field) != new_value or field in files]
            if not item.changes:
                raise ValidationError({"modifications": "Modifiez au moins un champ avant d’envoyer la proposition."})
            transaction.set_rollback(True)
    finally:
        # File storage is not transactional. Remove only files generated by this preview.
        for field, original in original_paths.items():
            candidate = getattr(preview_order, field)
            if candidate.name and candidate.name != original:
                candidate.storage.delete(candidate.name)
        order.refresh_from_db()
        order._prefetched_objects_cache = {}
        item.refresh_from_db(fields=["statut", "applied_at"])
        for uploaded in files.values():
            uploaded.seek(0)
    item.proposed_data = _json(data)
    item.save(update_fields=["proposed_data", "original_data", "changes"])
    stored = []
    try:
        for field, uploaded in files.items():
            document = LogisticsChangeRequestFile.objects.create(request=item, field=field,
                original_name=Path(uploaded.name).name, file=uploaded)
            stored.append(document)
    except Exception:
        for document in stored:
            document.file.delete(save=False)
        raise


def apply_proposal(order, item, request, apply_action):
    data = dict(item.proposed_data)
    documents = list(item.files.all())
    current_data = {**data, **{document.field: None for document in documents}}
    if state_for(order, current_data) != item.original_data:
        raise ValidationError({"modifications": "Des valeurs ont changé depuis cette proposition. Refusez-la et demandez une nouvelle proposition."})
    with ExitStack() as stack:
        files = {}
        for document in documents:
            opened = stack.enter_context(document.file.open("rb"))
            files[document.field] = File(opened.file, name=document.original_name)
        proposal = SimpleNamespace(user=request.user, data={**data, **files}, FILES=files, method="POST")
        apply_action(order, proposal, item)
