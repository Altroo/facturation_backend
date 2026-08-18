from datetime import datetime, timedelta, time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from account.models import CustomUser
from company.models import Company
from logistique.models import LogisticsOrder, LogisticsPaymentInstallment


DEMO_PREFIX = "DEMO-LOG-"


def add_months(date_value, months):
    month_index = date_value.month - 1 + months
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1
    return date_value.replace(year=year, month=month, day=1)


def make_aware_date(date_value):
    return timezone.make_aware(datetime.combine(date_value, time(hour=9)))


def build_demo_pdf(title):
    safe_title = title.replace("\\", "").replace("(", "[").replace(")", "]")[:120]
    stream = f"BT /F1 12 Tf 36 96 Td ({safe_title}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 144] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    body = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    xref += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return body + xref + trailer


def ensure_demo_document(relative_path, title):
    if not relative_path:
        return ""
    file_path = Path(settings.MEDIA_ROOT) / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_bytes(build_demo_pdf(title))
    return relative_path


class Command(BaseCommand):
    help = "Seed deterministic logistics demo orders for local dashboard testing."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--orders", type=int, default=36)
        parser.add_argument(
            "--keep-existing",
            action="store_true",
            help="Keep existing DEMO-LOG orders instead of replacing them.",
        )

    def handle(self, *args, **options):
        company_id = options["company_id"]
        orders_count = options["orders"]

        if orders_count < 6:
            raise CommandError("--orders must be at least 6 to exercise the charts.")

        company_qs = Company.objects.all().order_by("id")
        company = company_qs.filter(id=company_id).first() if company_id else company_qs.first()
        if not company:
            raise CommandError("No company found. Create a company before seeding logistics data.")

        if not options["keep_existing"]:
            deleted, _ = LogisticsOrder.objects.filter(
                company=company,
                numero_commande__startswith=DEMO_PREFIX,
            ).delete()
            self.stdout.write(f"Deleted {deleted} existing demo logistics rows.")

        responsible = (
            CustomUser.objects.filter(memberships__company=company).order_by("id").first()
            or CustomUser.objects.order_by("id").first()
        )

        today = timezone.localdate()
        current_month = today.replace(day=1)
        suppliers = [
            "Atlas Components",
            "Med Global Freight",
            "Iberia Packaging",
            "Nord Transit Supply",
            "Oceanic Trade Co",
        ]
        statuses = [
            "Réception commande",
            "Commande fournisseur",
            "Proforma",
            "Titre d'Importation",
            "Validation",
            "Paiement demandé",
            "Paiement effectué",
            "SWIFT / Draft LC",
            "Envoi SWIFT / Draft LC",
            "Production",
            "Expédition",
            "Documents originaux",
            "Transit",
            "Dédouanement",
            "Réception locale",
            "Livraison client",
            "Clôture",
        ]
        payment_methods = ["LC", "Virement", "Remise documentaire"]
        transports = ["Maritime", "Routier", "Aérien"]
        incoterms = ["FOB", "CIF", "EXW", "DAP"]
        origins = ["Espagne", "Italie", "Turquie", "Chine", "France"]

        created_orders = []
        for index in range(orders_count):
            order_number = f"{DEMO_PREFIX}{index + 1:03d}"
            month_start = add_months(current_month, -(index % 6))
            created_date = month_start + timedelta(days=min(24, 2 + (index * 3) % 25))
            created_at = make_aware_date(created_date)
            status = statuses[index % len(statuses)]
            supplier = suppliers[index % len(suppliers)]
            is_done = status in {"Livraison client", "Clôture"}
            is_payment_validated = statuses.index(status) >= statuses.index("Paiement effectué")
            is_payment_requested = statuses.index(status) >= statuses.index("Paiement demandé")

            if index % 11 == 0:
                payment_status = "Non demandé"
                bank_payment_status = "Bloqué"
                accounting_payment_status = "Paiement à traiter"
            elif is_payment_validated:
                payment_status = "Validé"
                bank_payment_status = "Exécuté"
                accounting_payment_status = "Paiement validé"
            elif is_payment_requested:
                payment_status = "En attente"
                bank_payment_status = "En validation"
                accounting_payment_status = "Paiement à traiter"
            else:
                payment_status = "Non demandé"
                bank_payment_status = "À préparer"
                accounting_payment_status = "Paiement à traiter"

            planned_date = created_date + timedelta(days=35 + (index % 5) * 4)
            if not is_done and index % 4 == 0:
                planned_date = today - timedelta(days=3 + index % 12)
            real_date = planned_date + timedelta(days=index % 6) if is_done else None

            purchase = Decimal("8500.00") + Decimal(index * 925)
            transport = Decimal("450.00") + Decimal((index % 5) * 180)
            transit = Decimal("300.00") + Decimal((index % 4) * 140)
            customs = Decimal("650.00") + Decimal((index % 6) * 215)
            vat = (purchase * Decimal("0.20")).quantize(Decimal("0.01"))
            local_delivery = Decimal("180.00") + Decimal((index % 3) * 90)
            other = Decimal("75.00") + Decimal((index % 7) * 35)
            total = purchase + transport + transit + customs + vat + local_delivery + other

            swift_file = ensure_demo_document(
                f"logistique_documents/demo-swift-{index + 1:03d}.pdf",
                f"{order_number} - SWIFT",
            ) if payment_status == "Validé" and index % 3 != 0 else ""
            original_docs = ensure_demo_document(
                f"logistique_documents/demo-docs-{index + 1:03d}.pdf",
                f"{order_number} - Documents originaux",
            ) if status not in {"Documents originaux", "Transit"} or index % 2 == 0 else ""

            order = LogisticsOrder.objects.create(
                company=company,
                numero_commande=order_number,
                fournisseur=supplier,
                devise="MAD",
                incoterm=incoterms[index % len(incoterms)],
                transport=transports[index % len(transports)],
                conditions_paiement=f"{payment_methods[index % len(payment_methods)]} - {30 + index % 4 * 15} jours",
                responsable=responsible,
                date_prevue=planned_date,
                date_reelle=real_date,
                statut=status,
                poids_net=Decimal("120.00") + Decimal(index * 8),
                poids_brut=Decimal("135.00") + Decimal(index * 9),
                volume=Decimal("3.500") + Decimal(index) / Decimal("10"),
                origine_marchandise=origins[index % len(origins)],
                nature_marchandise=f"Lot demo logistique {index + 1:03d}",
                numero_domiciliation=f"DOM-{today.year}-{index + 1:03d}",
                banque="BMCE" if index % 2 == 0 else "Attijariwafa Bank",
                montant_titre_importation=total,
                devise_titre_importation="MAD",
                date_titre_importation=created_date + timedelta(days=6),
                date_validation_titre_importation=created_date + timedelta(days=10)
                if statuses.index(status) >= statuses.index("Validation")
                else None,
                statut_titre_importation=(
                    "Titre d'import validé – En attente de paiement"
                    if is_payment_requested
                    else "À préparer"
                ),
                methode_paiement=payment_methods[index % len(payment_methods)],
                statut_paiement=payment_status,
                statut_banque_paiement=bank_payment_status,
                statut_traitement_paiement=accounting_payment_status,
                demande_paiement_envoyee_le=created_at + timedelta(days=12)
                if is_payment_requested
                else None,
                demande_paiement_envoyee_par=responsible if is_payment_requested else None,
                paiement_valide_le=created_at + timedelta(days=18)
                if payment_status == "Validé"
                else None,
                paiement_valide_par=responsible if payment_status == "Validé" else None,
                date_paiement=created_date + timedelta(days=18)
                if payment_status == "Validé"
                else None,
                montant_paiement=total if payment_status == "Validé" else Decimal("0.00"),
                reference_paiement=f"PAY-DEMO-{index + 1:03d}"
                if payment_status == "Validé"
                else "",
                date_upload_swift=created_at + timedelta(days=20) if swift_file else None,
                swift_envoye_fournisseur_le=created_at + timedelta(days=21)
                if swift_file and statuses.index(status) >= statuses.index("Envoi SWIFT / Draft LC")
                else None,
                cout_achat=purchase,
                cout_transport=transport,
                frais_transit=transit,
                frais_douane=customs,
                tva=vat,
                livraison_locale=local_delivery,
                autres_frais=other,
                cout_total=total,
                titre_importation_file=ensure_demo_document(
                    f"logistique_documents/demo-ti-{index + 1:03d}.pdf",
                    f"{order_number} - Titre d'Importation",
                ),
                proforma_fournisseur_file=ensure_demo_document(
                    f"logistique_documents/demo-proforma-{index + 1:03d}.pdf",
                    f"{order_number} - Proforma fournisseur",
                ),
                justificatifs_file=ensure_demo_document(
                    f"logistique_documents/demo-justif-{index + 1:03d}.pdf",
                    f"{order_number} - Justificatifs",
                ),
                swift_file=swift_file,
                documents_originaux_file=original_docs,
                created_by_user=responsible,
            )
            LogisticsOrder.objects.filter(pk=order.pk).update(
                date_created=created_at,
                date_updated=created_at,
            )
            if is_payment_requested:
                LogisticsPaymentInstallment.objects.create(
                    commande=order,
                    date_echeance=created_date + timedelta(days=18),
                    montant_prevu=total,
                    devise="MAD",
                    statut_traitement=accounting_payment_status,
                    date_paiement=(
                        created_date + timedelta(days=18)
                        if payment_status == "Validé"
                        else None
                    ),
                    montant_paye=total if payment_status == "Validé" else Decimal("0.00"),
                    reference_bancaire=(
                        f"PAY-DEMO-{index + 1:03d}"
                        if payment_status == "Validé"
                        else ""
                    ),
                    methode_paiement=order.methode_paiement,
                    justificatif_file=swift_file or None,
                    paiement_valide_le=(
                        created_at + timedelta(days=18)
                        if payment_status == "Validé"
                        else None
                    ),
                    paiement_valide_par=(
                        responsible if payment_status == "Validé" else None
                    ),
                    preuve_envoyee_fournisseur_le=order.swift_envoye_fournisseur_le,
                )
            created_orders.append(order.numero_commande)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(created_orders)} demo logistics orders for company {company.id} ({company.raison_sociale})."
            )
        )
