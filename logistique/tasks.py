from mimetypes import guess_type
from pathlib import Path

from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from account.models import Membership
from core.constants import ROLE_COMPTABLE
from facturation_backend.celery_conf import app

from .models import LogisticsOrder, LogisticsPaymentInstallment

logger = get_task_logger(__name__)


def _dossier_url(order):
    path = f"/dashboard/logistique/{order.id}?company_id={order.company_id}"
    frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
    return f"{frontend_url}{path}" if frontend_url else path


def _attach_file(message, file_field):
    if not file_field:
        return
    file_field.open("rb")
    try:
        content = file_field.read()
    finally:
        file_field.close()
    filename = Path(file_field.name).name
    message.attach(filename, content, guess_type(filename)[0])


def _accounting_message(order):
    subject = f"Paiement à effectuer – Dossier Import {order.numero_commande}"
    body = "\n".join(
        [
            "Bonjour,",
            "",
            "Une demande de paiement fournisseur est prête à être traitée.",
            "",
            f"Référence dossier : {order.numero_commande}",
            f"Fournisseur : {order.fournisseur}",
            (
                "Montant : "
                f"{order.montant_titre_importation:.2f} "
                f"{order.devise_titre_importation}"
            ),
            f"Référence titre d'importation : {order.numero_domiciliation}",
            f"Lien direct vers le dossier : {_dossier_url(order)}",
            "",
            "Le titre d'importation et la pro forma fournisseur sont joints à ce message.",
        ]
    )
    return subject, body


def _supplier_message(order, installment):
    subject = f"Justificatif de paiement – Dossier import {order.numero_commande}"
    body = "\n".join(
        [
            f"Bonjour {order.fournisseur},",
            "",
            "Veuillez trouver en pièce jointe le justificatif de notre paiement.",
            "",
            f"Référence dossier : {order.numero_commande}",
            ("Montant payé : " f"{installment.montant_paye:.2f} {installment.devise}"),
            f"Référence bancaire : {installment.reference_bancaire}",
            "",
            "Merci de bien vouloir confirmer sa réception.",
        ]
    )
    return subject, body


def _active_accounting_recipients(company_id):
    return list(
        Membership.objects.filter(
            company_id=company_id,
            role__name=ROLE_COMPTABLE,
            user__is_active=True,
        )
        .exclude(user__email="")
        .order_by("user_id")
        .values_list("user__email", flat=True)
        .distinct()
    )


def _claim_is_fresh(status, claimed_at):
    if status != "Envoi en cours" or not claimed_at:
        return False
    return claimed_at > timezone.now() - LogisticsOrder.EMAIL_DELIVERY_CLAIM_TIMEOUT


def queue_accounting_payment_email(order_id, delivery_token):
    try:
        deliver_accounting_payment_email.delay(order_id, delivery_token)
    except Exception as exc:  # broker failures must remain visible and retryable
        logger.exception(
            "Unable to queue accounting payment email for order %s", order_id
        )
        LogisticsOrder.objects.filter(
            pk=order_id,
            demande_paiement_email_statut="En attente",
            demande_paiement_email_file_token=delivery_token,
        ).update(
            demande_paiement_email_statut="Échec",
            demande_paiement_email_erreur=str(exc),
            demande_paiement_email_task_id="",
            demande_paiement_email_prise_en_charge_le=None,
            demande_paiement_email_file_token="",
            demande_paiement_email_mis_en_file_le=None,
        )


def queue_supplier_payment_proof_email(installment_id, delivery_token):
    try:
        deliver_supplier_payment_proof_email.delay(installment_id, delivery_token)
    except Exception as exc:  # broker failures must remain visible and retryable
        logger.exception(
            "Unable to queue supplier payment proof email for installment %s",
            installment_id,
        )
        LogisticsPaymentInstallment.objects.filter(
            pk=installment_id,
            preuve_email_statut="En attente",
            preuve_email_file_token=delivery_token,
        ).update(
            preuve_email_statut="Échec",
            preuve_email_erreur=str(exc),
            preuve_email_task_id="",
            preuve_email_prise_en_charge_le=None,
            preuve_email_file_token="",
            preuve_email_mise_en_file_le=None,
        )


def _claim_accounting_delivery(order_id, delivery_token, task_id):
    with transaction.atomic():
        order = LogisticsOrder.objects.select_for_update().get(pk=order_id)
        if order.demande_paiement_email_statut == "Envoyé":
            return None
        if order.demande_paiement_email_file_token != delivery_token:
            return None
        if order.demande_paiement_email_statut not in {
            "En attente",
            "Envoi en cours",
            "Échec",
        }:
            return None
        if _claim_is_fresh(
            order.demande_paiement_email_statut,
            order.demande_paiement_email_prise_en_charge_le,
        ):
            return None
        if order.statut_global == "Annulé" or order.statut_paiement != "En attente":
            order.demande_paiement_email_statut = "Échec"
            order.demande_paiement_email_erreur = (
                "Envoi annulé car le dossier ou le paiement n'est plus actif."
            )
            order.demande_paiement_email_file_token = ""
            order.demande_paiement_email_mis_en_file_le = None
            order.save(
                update_fields=[
                    "demande_paiement_email_statut",
                    "demande_paiement_email_erreur",
                    "demande_paiement_email_file_token",
                    "demande_paiement_email_mis_en_file_le",
                    "date_updated",
                ]
            )
            return None

        recipients = _active_accounting_recipients(order.company_id)
        if not recipients:
            order.demande_paiement_email_statut = "Échec"
            order.demande_paiement_email_erreur = (
                "Aucune adresse e-mail comptable active n'est disponible."
            )
            order.demande_paiement_email_destinataires = []
            order.demande_paiement_email_task_id = ""
            order.demande_paiement_email_prise_en_charge_le = None
            order.demande_paiement_email_file_token = ""
            order.demande_paiement_email_mis_en_file_le = None
            order.save(
                update_fields=[
                    "demande_paiement_email_statut",
                    "demande_paiement_email_erreur",
                    "demande_paiement_email_destinataires",
                    "demande_paiement_email_task_id",
                    "demande_paiement_email_prise_en_charge_le",
                    "demande_paiement_email_file_token",
                    "demande_paiement_email_mis_en_file_le",
                    "date_updated",
                ]
            )
            return None

        order.demande_paiement_email_statut = "Envoi en cours"
        order.demande_paiement_email_destinataires = recipients
        order.demande_paiement_email_tentatives += 1
        order.demande_paiement_email_erreur = ""
        order.demande_paiement_email_task_id = task_id
        order.demande_paiement_email_prise_en_charge_le = timezone.now()
        order.save(
            update_fields=[
                "demande_paiement_email_statut",
                "demande_paiement_email_destinataires",
                "demande_paiement_email_tentatives",
                "demande_paiement_email_erreur",
                "demande_paiement_email_task_id",
                "demande_paiement_email_prise_en_charge_le",
                "date_updated",
            ]
        )
        return order


def _finalize_accounting_delivery(order_id, task_id, error=None):
    with transaction.atomic():
        order = LogisticsOrder.objects.select_for_update().get(pk=order_id)
        if (
            order.demande_paiement_email_statut != "Envoi en cours"
            or order.demande_paiement_email_task_id != task_id
        ):
            return False

        order.demande_paiement_email_task_id = ""
        order.demande_paiement_email_prise_en_charge_le = None
        if error:
            order.demande_paiement_email_statut = "Échec"
            order.demande_paiement_email_erreur = str(error)
        else:
            order.demande_paiement_email_statut = "Envoyé"
            order.demande_paiement_email_erreur = ""
            order.demande_paiement_envoyee_le = timezone.now()
            order.demande_paiement_email_file_token = ""
            order.demande_paiement_email_mis_en_file_le = None
        order.save(
            update_fields=[
                "demande_paiement_email_statut",
                "demande_paiement_email_erreur",
                "demande_paiement_envoyee_le",
                "demande_paiement_email_task_id",
                "demande_paiement_email_prise_en_charge_le",
                "demande_paiement_email_file_token",
                "demande_paiement_email_mis_en_file_le",
                "date_updated",
            ]
        )
        if not error:
            order.add_event(
                user=order.demande_paiement_envoyee_par,
                action="E-mail Service Comptable envoyé",
                new_value=", ".join(order.demande_paiement_email_destinataires),
            )
        return True


@app.task(
    bind=True,
    serializer="json",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def deliver_accounting_payment_email(self, order_id, delivery_token):
    task_id = self.request.id or f"accounting-{order_id}"
    order = _claim_accounting_delivery(order_id, delivery_token, task_id)
    if not order:
        return

    delivery_error = None
    try:
        subject, body = _accounting_message(order)
        message = EmailMessage(
            subject=subject,
            body=body,
            to=order.demande_paiement_email_destinataires,
        )
        _attach_file(message, order.proforma_fournisseur_file)
        _attach_file(message, order.titre_importation_file)
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("Le serveur e-mail n'a confirmé aucun envoi.")
    except Exception as exc:
        delivery_error = exc

    finalized = _finalize_accounting_delivery(order_id, task_id, error=delivery_error)
    if delivery_error and finalized:
        logger.error(
            "Accounting payment email failed for order %s: %s",
            order_id,
            delivery_error,
        )
        raise self.retry(exc=delivery_error, countdown=60)


def _claim_supplier_delivery(installment_id, delivery_token, task_id):
    order_id = LogisticsPaymentInstallment.objects.values_list(
        "commande_id", flat=True
    ).get(pk=installment_id)
    with transaction.atomic():
        order = LogisticsOrder.objects.select_for_update().get(pk=order_id)
        installment = LogisticsPaymentInstallment.objects.select_for_update().get(
            pk=installment_id
        )
        if installment.preuve_email_statut == "Envoyé":
            return None
        if installment.preuve_email_file_token != delivery_token:
            return None
        if installment.preuve_email_statut not in {
            "En attente",
            "Envoi en cours",
            "Échec",
        }:
            return None
        if _claim_is_fresh(
            installment.preuve_email_statut,
            installment.preuve_email_prise_en_charge_le,
        ):
            return None
        if (
            order.statut_global == "Annulé"
            or order.statut_banque_paiement == "Bloqué"
            or not installment.paiement_valide_le
            or installment.reception_confirmee_le
        ):
            installment.preuve_email_statut = "Échec"
            installment.preuve_email_erreur = (
                "Envoi annulé car le dossier ou le paiement n'est plus actif."
            )
            installment.preuve_email_file_token = ""
            installment.preuve_email_mise_en_file_le = None
            installment.save(
                update_fields=[
                    "preuve_email_statut",
                    "preuve_email_erreur",
                    "preuve_email_file_token",
                    "preuve_email_mise_en_file_le",
                    "date_updated",
                ]
            )
            return None

        recipient = (order.fournisseur_email or "").strip()
        if not recipient or not installment.justificatif_file:
            installment.preuve_email_statut = "Échec"
            installment.preuve_email_erreur = (
                "L'adresse fournisseur ou le justificatif de paiement est manquant."
            )
            installment.preuve_email_destinataire = recipient
            installment.preuve_email_task_id = ""
            installment.preuve_email_prise_en_charge_le = None
            installment.preuve_email_file_token = ""
            installment.preuve_email_mise_en_file_le = None
            installment.save(
                update_fields=[
                    "preuve_email_statut",
                    "preuve_email_erreur",
                    "preuve_email_destinataire",
                    "preuve_email_task_id",
                    "preuve_email_prise_en_charge_le",
                    "preuve_email_file_token",
                    "preuve_email_mise_en_file_le",
                    "date_updated",
                ]
            )
            return None

        installment.preuve_email_statut = "Envoi en cours"
        installment.preuve_email_destinataire = recipient
        installment.preuve_email_tentatives += 1
        installment.preuve_email_erreur = ""
        installment.preuve_email_task_id = task_id
        installment.preuve_email_prise_en_charge_le = timezone.now()
        installment.save(
            update_fields=[
                "preuve_email_statut",
                "preuve_email_destinataire",
                "preuve_email_tentatives",
                "preuve_email_erreur",
                "preuve_email_task_id",
                "preuve_email_prise_en_charge_le",
                "date_updated",
            ]
        )
        return order, installment


def _finalize_supplier_delivery(installment_id, task_id, error=None):
    order_id = LogisticsPaymentInstallment.objects.values_list(
        "commande_id", flat=True
    ).get(pk=installment_id)
    with transaction.atomic():
        order = LogisticsOrder.objects.select_for_update().get(pk=order_id)
        installment = LogisticsPaymentInstallment.objects.select_for_update().get(
            pk=installment_id
        )
        if (
            installment.preuve_email_statut != "Envoi en cours"
            or installment.preuve_email_task_id != task_id
        ):
            return False

        installment.preuve_email_task_id = ""
        installment.preuve_email_prise_en_charge_le = None
        if error:
            installment.preuve_email_statut = "Échec"
            installment.preuve_email_erreur = str(error)
        else:
            sent_at = timezone.now()
            installment.preuve_email_statut = "Envoyé"
            installment.preuve_email_erreur = ""
            installment.preuve_envoyee_fournisseur_le = sent_at
            installment.preuve_email_file_token = ""
            installment.preuve_email_mise_en_file_le = None
            order.swift_envoye_fournisseur_le = sent_at
            order.statut = "Envoi SWIFT / Draft LC"
            order.sync_global_status(preserve_manual=False, commit=False)
            order.save(
                update_fields=[
                    "swift_envoye_fournisseur_le",
                    "statut",
                    "statut_global",
                    "date_updated",
                ]
            )
        installment.save(
            update_fields=[
                "preuve_email_statut",
                "preuve_email_erreur",
                "preuve_envoyee_fournisseur_le",
                "preuve_email_task_id",
                "preuve_email_prise_en_charge_le",
                "preuve_email_file_token",
                "preuve_email_mise_en_file_le",
                "date_updated",
            ]
        )
        if not error:
            order.add_event(
                user=installment.preuve_email_demandee_par,
                action="Envoi preuve fournisseur",
                new_value=installment.preuve_email_destinataire,
            )
        return True


@app.task(
    bind=True,
    serializer="json",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def deliver_supplier_payment_proof_email(self, installment_id, delivery_token):
    task_id = self.request.id or f"supplier-{installment_id}"
    claimed = _claim_supplier_delivery(installment_id, delivery_token, task_id)
    if not claimed:
        return
    order, installment = claimed

    delivery_error = None
    try:
        subject, body = _supplier_message(order, installment)
        message = EmailMessage(
            subject=subject,
            body=body,
            to=[installment.preuve_email_destinataire],
        )
        _attach_file(message, installment.justificatif_file)
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("Le serveur e-mail n'a confirmé aucun envoi.")
    except Exception as exc:
        delivery_error = exc

    finalized = _finalize_supplier_delivery(
        installment_id, task_id, error=delivery_error
    )
    if delivery_error and finalized:
        logger.error(
            "Supplier payment proof email failed for installment %s: %s",
            installment_id,
            delivery_error,
        )
        raise self.retry(exc=delivery_error, countdown=60)
