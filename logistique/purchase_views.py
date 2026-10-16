from datetime import date, datetime
from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from core.views import CompanyAccessMixin
from article.models import Article
from parameter.models import Marque
from stock.services import activate_incoming, validate_receipt
from stock.serializers import StockReceiptSerializer
from .models import LogisticsOrder, LogisticsOrderLine, LogisticsProcessNote
from .serializers import LogisticsOrderDetailSerializer, LogisticsOrderUpdateSerializer, LOGISTICS_IMPORT_TITLE_FIELDS, validate_logistics_document
from .purchase_serializers import PurchaseDossierSerializer, PurchaseProformaSerializer, PurchaseProgressSerializer
from .purchase import CONDITIONS, create_purchase_schedule, validate_purchase_transition, preparation_blocker
from .utils import get_next_numero_logistique


_BUSINESS_FIELDS = {
    "fournisseur": "Fournisseur",
    "fournisseur_email": "E-mail du fournisseur",
    "marque": "Contact fournisseur",
    "responsable": "Responsable du dossier",
    "date_prevue": "Date prévue du dossier",
    "date_commande_client": "Date de commande client",
    "numero_proforma_fournisseur": "Numéro de proforma fournisseur",
    "date_proforma_fournisseur": "Date de proforma fournisseur",
    "montant_proforma_fournisseur": "Montant de proforma fournisseur",
    "devise_proforma_fournisseur": "Devise de proforma fournisseur",
    "condition_achat": "Conditions d’achat",
    "incoterm": "Incoterm",
    "delai_proforma_jours": "Délai fournisseur (jours)",
    "origine_marchandise": "Origine de la marchandise",
    "nature_marchandise": "Nature de la marchandise",
    "poids_net": "Poids net (kg)",
    "poids_brut": "Poids brut (kg)",
    "volume": "Volume (m³)",
    "ecart_prix_proforma": "Anomalie de prix",
    "ecart_quantite_proforma": "Anomalie de quantité",
    "ecart_autre_proforma": "Autre anomalie",
    "notes_ecarts_proforma": "Détail des anomalies / motif",
    "statut_proforma_conformite": "Décision sur la proforma fournisseur",
    "proforma_fournisseur_file": "Proforma fournisseur jointe",
    "numero_domiciliation": "Numéro de domiciliation",
    "banque": "Banque",
    "montant_titre_importation": "Montant du titre d’importation",
    "devise_titre_importation": "Devise du titre d’importation",
    "date_titre_importation": "Date du titre d’importation",
    "titre_importation_file": "Titre d’importation joint",
    "date_expedition_prevue": "Date d’expédition prévue",
    "production_confirmee_le": "Début de production confirmé",
    "date_expedition_reelle": "Date réelle d’expédition",
    "date_arrivee_maroc": "Date d’arrivée au Maroc",
    "documents_remis_banque_le": "Documents remis à la banque le",
    "date_reelle": "Date réelle de réception",
    "transport": "Transport",
    "documents_originaux_requis": "Documents originaux requis",
    "statut_documents_originaux": "État des documents originaux",
    "documents_originaux_file": "Documents originaux joints",
    "justificatifs_file": "Justificatif joint",
    "cout_transport": "Coût du transport",
    "frais_transit": "Frais de transit",
    "frais_douane": "Droits de douane",
    "tva": "TVA",
    "livraison_locale": "Coût de livraison locale",
    "autres_frais": "Autres frais",
    "statut": "Phase du dossier",
}


def _history_value(value):
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%d/%m/%Y à %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if hasattr(value, "name"):
        return Path(value.name).name if value.name else ""
    return str(value)


def _business_snapshot(order, *, include_lines=False):
    values = {field: _history_value(getattr(order, field)) for field in _BUSINESS_FIELDS}
    responsible = order.responsable
    values["responsable"] = (
        f"{responsible.first_name} {responsible.last_name}".strip() or responsible.email
        if responsible else ""
    )
    values["condition_achat"] = CONDITIONS.get(order.condition_achat, (order.condition_achat,))[0]
    if include_lines:
        values["lignes"] = "\n".join(
            f"{line.article_reference or line.article_id} : {line.designation} ; "
            f"quantité {line.quantity} ; prix d’achat {line.prix_achat} {line.devise_prix_achat}"
            + (f" ; emplacement {line.expected_emplacement}" if line.expected_emplacement_id else "")
            for line in order.lignes.select_related("expected_emplacement").order_by("id")
        )
    return values


def _record_business_changes(order, before, *, user, uploaded_fields=()):
    after = _business_snapshot(order, include_lines="lignes" in before)
    recorded = 0
    for field, old_value in before.items():
        new_value = after[field]
        replaced_file = field in uploaded_fields
        if old_value == new_value and not replaced_file:
            continue
        label = _BUSINESS_FIELDS.get(field, "Articles de la proforma fournisseur")
        note = "Document remplacé." if replaced_file and old_value == new_value else ""
        if len(old_value) > 255 or len(new_value) > 255:
            note = f"Ancienne valeur :\n{old_value or 'Non renseigné'}\n\nNouvelle valeur :\n{new_value or 'Non renseigné'}"
        order.add_event(user=user, action=f"Modification : {label}",
            old_value=old_value[:255], new_value=new_value[:255], note=note)
        recorded += 1
    return recorded


def create_purchase_dossier(company_id, user, data):
    serializer = PurchaseDossierSerializer(data=data, context={"company_id": company_id, "create": True})
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data.copy()
    supplier = values.pop("fournisseur_record", None)
    brand_id = values.pop("marque", None)
    responsible_id = values.pop("responsable", None) or user.pk
    brand = Marque.objects.filter(pk=brand_id, company_id=company_id).first() if brand_id else None
    if "fournisseur_email" not in values and brand:
        values["fournisseur_email"] = brand.email
    with transaction.atomic():
        # Number allocation also locks the company when no dossier exists yet.
        from company.models import Company
        Company.objects.select_for_update().get(pk=company_id)
        from .suppliers import ensure_supplier
        supplier = supplier or ensure_supplier(company_id, values["fournisseur"], values.get("fournisseur_email", ""))
        order = LogisticsOrder.objects.create(company_id=company_id, fournisseur_record=supplier,
            numero_commande=get_next_numero_logistique(company_id), workflow_version=2,
            responsable_id=responsible_id, marque=brand, created_by_user=user,
            statut_commande_lancement="Terminée", statut="Proforma", statut_global="En attente externe", **values)
        order.add_event(user=user, action="Création du dossier fournisseur", new_value=order.numero_commande)
    return [order]


class PurchaseWorkflowView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request, pk):
        from .views import LogisticsOrderDetailEditDeleteView, _can_manage_logistics, _ensure_order_active
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied("Vous n’avez pas les droits pour modifier ce dossier.")
        _ensure_order_active(order)
        if not order.is_supplier_purchase:
            if request.data.get("action") != "adopter_parcours_fournisseur":
                raise ValidationError({"dossier": "Complétez d’abord les informations du dossier pour utiliser le parcours d’achat fournisseur."})
            from .compatibility import adopt_supplier_workflow
            adopt_supplier_workflow(order, user=request.user, data=request.data)
            order.sync_global_status(preserve_manual=False)
            order = LogisticsOrderDetailEditDeleteView.get_object(pk)
            return Response(LogisticsOrderDetailSerializer(order, context={"request": request}).data)
        if order.statut == "Clôture" and request.data.get("action") != "relancer_notification":
            raise ValidationError({"dossier": "Ce dossier est clôturé."})
        action = request.data.get("action")
        before = _business_snapshot(order, include_lines=action == "proforma") if action in {"dossier", "proforma", "titre", "progression"} else None
        if action == "dossier":
            serializer = PurchaseDossierSerializer(data=request.data, context={"company_id": order.company_id})
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data.copy()
            supplier = values.pop("fournisseur_record", None)
            old_name = order.fournisseur
            for field, value in values.items():
                setattr(order, {"responsable": "responsable_id", "marque": "marque_id"}.get(field, field), value)
            if supplier:
                order.fournisseur_record = supplier
            elif order.fournisseur != old_name or not order.fournisseur_record_id:
                from .suppliers import ensure_supplier
                order.fournisseur_record = ensure_supplier(order.company_id, order.fournisseur, order.fournisseur_email)
            order.save()
        elif action == "proforma":
            if order.is_proforma_step_complete:
                raise ValidationError({"proforma": "La proforma fournisseur est déjà validée."})
            if order.legacy_source_snapshot and order.lignes.filter(
                Q(proforma__isnull=False) | Q(source_line__isnull=False) | Q(client__isnull=False)
            ).exists() and "lignes" not in request.data:
                raise ValidationError({"lignes": "Renseignez les quantités et prix de la proforma fournisseur. Les anciennes lignes client ne sont pas des achats confirmés."})
            data = request.data.copy()
            data["action"] = request.data.get("decision", "control")
            serializer = PurchaseProformaSerializer(data=data, context={"order": order})
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data.copy()
            decision = values.pop("action")
            lines = values.pop("lignes", None)
            for field, value in values.items():
                setattr(order, field, value)
            order.devise = order.devise_proforma_fournisseur
            _, advance, method, _ = CONDITIONS[order.condition_achat]
            order.avance_pourcentage = advance
            order.methode_paiement = method
            if lines is not None:
                from stock.models import StockReceiptLine
                if StockReceiptLine.objects.filter(logistics_line__commande=order).exists():
                    raise ValidationError({"lignes": "Des réceptions utilisent déjà ces lignes. Elles ne peuvent plus être remplacées."})
                order.lignes.all().delete()
                articles = Article.objects.in_bulk([line["article"] for line in lines])
                for line in lines:
                    article = articles[line["article"]]
                    LogisticsOrderLine.objects.create(commande=order, article=article,
                        article_reference=article.reference, designation=article.designation,
                        marque_name=str(article.marque) if article.marque_id else "",
                        quantity=line["quantity"], prix_achat=line["prix_achat"],
                        devise_prix_achat=order.devise, expected_emplacement_id=line.get("expected_emplacement") or article.emplacement_id)
            getattr(order, "_prefetched_objects_cache", {}).pop("lignes", None)
            order.statut_proforma_conformite = {"control": "En contrôle", "request_correction": "Correction demandée", "validate": "Validée", "reject": "Refusée"}[decision]
            order.proforma_controlee_le = timezone.now()
            order.proforma_controlee_par = request.user
            if decision == "validate":
                order.proforma_validee_le = timezone.now()
                order.proforma_validee_par = request.user
                create_purchase_schedule(order)
                getattr(order, "_prefetched_objects_cache", {}).pop("echeances_paiement", None)
                activate_incoming(order)
            order.save()
        elif action == "titre":
            allowed = LOGISTICS_IMPORT_TITLE_FIELDS - {"date_validation_titre_importation", "statut_titre_importation", "methode_paiement", "avance_pourcentage"}
            values = {key: value for key, value in request.data.items() if key in allowed}
            serializer = LogisticsOrderUpdateSerializer(order, data=values, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        elif action == "progression":
            serializer = PurchaseProgressSerializer(data=request.data, context={"order": order})
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data.copy()
            remark = values.pop("remarque", "").strip()
            confirm = values.pop("confirmer_production", False)
            target = values.pop("statut", "Expédition" if values.get("date_expedition_reelle") and not order.date_expedition_reelle else order.statut)
            for field, value in values.items():
                setattr(order, field, value)
            if confirm:
                reason = preparation_blocker(order)
                if reason:
                    raise ValidationError({"production": reason})
                order.production_confirmee_le = order.production_confirmee_le or timezone.now()
                target = "Production"
            validate_purchase_transition(order, target)
            order.statut = target
            order.save()
            if remark:
                note = LogisticsProcessNote.objects.create(commande=order, user=request.user, statut=order.statut, remarque=(f"Retard d’expédition ({order.date_expedition_prevue}) : " + remark if order.date_expedition_prevue and (order.date_expedition_reelle or timezone.localdate()) > order.date_expedition_prevue else remark))
                order.add_event(user=request.user,
                    action="Explication du retard d’expédition" if note.remarque.startswith("Retard d’expédition (") else "Remarque ajoutée au dossier",
                    note=note.remarque)
        elif action == "reception":
            validate_purchase_transition(order, "Expédition", enforce_sequence=False)
            data = {"logistics_order": order.pk, "reference": request.data.get("reference", ""), "note": request.data.get("note", ""), "lines": request.data.get("lines", [])}
            serializer = StockReceiptSerializer(data=data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            receipt = serializer.save()
            validate_receipt(receipt, request.user)
            details = [f"Référence : {receipt.reference or f'Réception #{receipt.pk}'}", "Quantités reçues :"]
            for line in receipt.lines.select_related("article", "emplacement", "logistics_line").order_by("id"):
                details.append(
                    f"- {line.article.reference} : {line.quantity} ; emplacement {line.emplacement} ; "
                    f"total reçu {line.logistics_line.received_quantity} / {line.logistics_line.quantity}"
                )
            if receipt.note:
                details.append(f"Note de réception :\n{receipt.note}")
            order.add_event(user=request.user, action="Réception de marchandises",
                new_value=(receipt.reference or f"Réception #{receipt.pk}")[:255], note="\n".join(details))
            order.refresh_from_db()
        elif action == "relancer_notification":
            from .tasks import queue_purchase_creator_email
            try:
                item = order.echeances_paiement.get(pk=request.data.get("echeance_id"), paiement_valide_le__isnull=False)
            except (ValueError, TypeError, order.echeances_paiement.model.DoesNotExist):
                raise ValidationError({"echeance_id": "Paiement validé introuvable."})
            transaction.on_commit(lambda: queue_purchase_creator_email(item.pk))
            order.add_event(user=request.user, action="Relance de la notification au créateur demandée",
                new_value=f"Paiement de {item.montant_paye:.2f} {item.devise}")
        else:
            raise ValidationError({"action": "Action inconnue."})
        if before is not None:
            recorded = _record_business_changes(order, before, user=request.user, uploaded_fields=request.FILES)
            if action == "proforma" and not recorded:
                description = {
                    "control": "Contrôle de la proforma fournisseur enregistré",
                    "request_correction": "Correction de la proforma fournisseur demandée",
                    "validate": "Proforma fournisseur validée",
                    "reject": "Proforma fournisseur refusée",
                }[decision]
                order.add_event(user=request.user, action=description,
                    new_value=order.numero_proforma_fournisseur)
        order.sync_global_status(preserve_manual=False)
        # Reload relation caches after changes to avoid returning stale form data.
        order = LogisticsOrderDetailEditDeleteView.get_object(pk)
        return Response(LogisticsOrderDetailSerializer(order, context={"request": request}).data)


class ImportTitleExtractView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, pk):
        from .views import LogisticsOrderDetailEditDeleteView, _can_manage_logistics
        from .import_title import extract_import_title
        order = LogisticsOrderDetailEditDeleteView.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied("Vous n’avez pas les droits pour lire ce titre d’importation.")
        file = request.FILES.get("file")
        if not file:
            raise ValidationError({"file": "Joignez le titre d’importation."})
        validate_logistics_document(file)
        return Response(extract_import_title(file))


def request_purchase_payment(order, request):
    from .views import _get_locked_installment, _assign_payment_task, _clear_payment_installment_cache
    from .purchase import payment_blocker
    from .services import send_payment_request_email
    from rest_framework import serializers
    class RequestSerializer(serializers.Serializer):
        echeance_id = serializers.IntegerField(min_value=1)
        date_echeance = serializers.DateField()
    serializer = RequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    item = _get_locked_installment(order, serializer.validated_data["echeance_id"])
    if item.demandee_le or item.paiement_valide_le:
        raise ValidationError({"paiement": "Cette échéance a déjà été transmise."})
    reason = payment_blocker(order, item)
    if reason:
        raise ValidationError({"paiement": reason})
    if order.demande_paiement_email_statut in {"En attente", "Envoi en cours"}:
        raise ValidationError({"email": "Attendez la fin de l’envoi de la demande précédente."})
    if not (order.numero_domiciliation.strip() and order.banque.strip() and order.date_titre_importation and order.titre_importation_file):
        raise ValidationError({"titre": "Renseignez et vérifiez le titre d’importation avant la demande de paiement."})
    if order.montant_titre_importation != order.payment_total or order.devise_titre_importation != order.devise_proforma_fournisseur:
        raise ValidationError({"titre": "Vérifiez le montant et la devise du titre d’importation : ils doivent correspondre à la proforma fournisseur."})
    item.date_echeance = serializer.validated_data["date_echeance"]
    item.demandee_le = timezone.now()
    item.save(update_fields=["date_echeance", "demandee_le", "date_updated"])
    _clear_payment_installment_cache(order)
    _assign_payment_task(order)
    order.date_validation_titre_importation = order.date_validation_titre_importation or timezone.localdate()
    order.statut_titre_importation = "Titre d'import validé – En attente de paiement"
    order.statut_banque_paiement = "En validation"
    order.statut_traitement_paiement = "Paiement à traiter"
    order.save()
    send_payment_request_email(order, request_user=request.user)
    return Response(LogisticsOrderDetailSerializer(order, context={"request": request}).data)


class SupplierDirectoryView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request):
        from .views import _can_manage_logistics
        from parameter.serializers import MarqueSerializer
        company_id = self._parse_company_id(request.query_params.get("company_id"), error_message="company_id est requis.")
        self._check_company_access(request, company_id)
        if not _can_manage_logistics(request.user, company_id):
            raise PermissionDenied("Vous n’avez pas les droits pour modifier le répertoire fournisseur.")
        instance = None
        if request.data.get("id"):
            from rest_framework import serializers
            identifier = serializers.IntegerField(min_value=1).run_validation(request.data["id"])
            instance = Marque.objects.select_for_update().filter(pk=identifier, company_id=company_id).first()
            if not instance:
                raise ValidationError({"id": "Cette marque n’appartient pas à cette société."})
        serializer = MarqueSerializer(instance, data={"nom": request.data.get("nom", ""), "email": request.data.get("email", ""), "company": company_id})
        serializer.is_valid(raise_exception=True)
        contact = serializer.save()
        from .suppliers import ensure_supplier
        ensure_supplier(company_id, contact.nom, contact.email)
        return Response(serializer.data)
