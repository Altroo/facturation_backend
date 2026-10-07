"""Prepare, review and apply resumable spelling corrections using only the private AI."""

import fcntl
import hashlib
import json
import os
import time
from copy import deepcopy
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import CharField, TextField

# Business prose only. Never credentials, codes, financial values, parties or history.
MODEL_NAMES = {
    "article",
    "devi",
    "factureclient",
    "factureproforma",
    "factureavoir",
    "bondelivraison",
    "reglement",
    "logisticsorder",
    "stockreceipt",
    "inventorysession",
    "inventoryline",
    "project",
    "projectpaymentschedule",
    "projectrealbudgetentry",
    "quote",
    "expense",
    "revenue",
    "projectattachment",
    "quoteattachment",
    "expenseattachment",
    "revenueattachment",
    "contract",
    "reservation",
    "cost",
    "hiltonreport",
    "hiltonreportmanualline",
    "product",
    "category",
    "promotion",
    "purchase",
    "stocktransfer",
    "stockaddrequest",
    "sale",
}
TEXT_NAMES = {
    "description",
    "designation",
    "remarque",
    "termes_paiement",
    "libelle",
    "notes",
    "note",
    "label",
    "title",
    "element",
    "conditions_paiement",
    "nature_marchandise",
    "notes_ecarts_proforma",
    "notes_suivi",
    "description_travaux",
    "conditions_acces",
    "clause_spec",
    "exclusions",
    "annexes",
    "materiaux_detail",
    "exclusions_garantie",
    "st_lot_description",
    "st_observations",
    "st_qualite",
    "cost_period_label",
    "rejection_reason",
    "cancellation_reason",
    "void_reason",
}
JSON_TEXT_FIELDS = {
    "prestations": ("nom", "description", "desc", "unite"),
    "tranches": ("label",),
    "st_tranches": ("label",),
}


def editable_fields(model):
    if model._meta.model_name not in MODEL_NAMES or model._meta.app_label in {
        "accounts",
        "auth",
        "admin",
        "notification",
    }:
        return []
    fields = []
    for field in model._meta.concrete_fields:
        text_name = field.name in TEXT_NAMES or (
            field.name.startswith("notes_") and isinstance(field, TextField)
        )
        product_name = (
            model._meta.model_name in {"product", "category", "promotion"}
            and field.name == "name"
        )
        if (
            isinstance(field, (CharField, TextField))
            and (text_name or product_name)
            and not field.choices
            and not field.unique
        ):
            fields.append(field)
        elif model._meta.model_name == "contract" and field.name in JSON_TEXT_FIELDS:
            fields.append(field)
    return fields


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def correct_text(text, protected_terms):
    if not text or not text.strip():
        return text
    try:
        from ai_assistant.client import AiAssistantClient

        assistant = AiAssistantClient()
    except ImportError:
        from ai_assistant.service import AiAssistantService

        assistant = AiAssistantService()
    # Keep line structure and never send a request larger than the model contract.
    remaining, parts = text, []
    while len(remaining) > 4500:
        boundary = max(remaining.rfind("\n", 0, 4500), remaining.rfind(" ", 0, 4500))
        if boundary <= 0:
            raise ValueError("Texte sans séparation trop long")
        parts.append(remaining[:boundary])
        remaining = remaining[boundary:]
    parts.append(remaining)
    corrected = []
    for part in parts:
        if not part.strip():
            corrected.append(part)
            continue
        for attempt in range(3):
            try:
                response = assistant.assist(
                    action="fix_grammar",
                    text=part.strip(),
                    source_language="auto",
                    context="spelling_cleanup",
                    protected_terms=protected_terms,
                )
                break
            except Exception as exc:
                if attempt == 2:
                    raise
                # Respect private gateway throttling without flooding the models.
                delay = min(float(getattr(exc, "wait", None) or 5 * (attempt + 1)), 65)
                time.sleep(delay)
        suggestion = response.get("suggested_text")
        if not isinstance(suggestion, str) or not suggestion.strip():
            raise ValueError("Réponse IA vide")
        corrected.append(
            part[: len(part) - len(part.lstrip())]
            + suggestion.strip()
            + part[len(part.rstrip()) :]
        )
    return "".join(corrected)


def correct_value(value, field, protected_terms):
    if field.name in JSON_TEXT_FIELDS:
        result = deepcopy(value)
        if not isinstance(result, list):
            return value
        for row in result:
            if isinstance(row, dict):
                for key in JSON_TEXT_FIELDS[field.name]:
                    if isinstance(row.get(key), str):
                        row[key] = correct_text(row[key], protected_terms)
        return result
    result = correct_text(value, protected_terms)
    if field.max_length and len(result) > field.max_length:
        raise ValueError("Correction trop longue pour ce champ")
    return result


def write_record(stream, record):
    stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def save_field(model, pk, field_name, expected, replacement):
    with transaction.atomic():
        obj = model.objects.select_for_update().filter(pk=pk).first()
        if obj is None:
            return "introuvable"
        current = getattr(obj, field_name)
        if current == replacement:
            return "done (déjà appliqué)"
        if current != expected:
            return "conflit (modifié depuis la préparation)"
        setattr(obj, field_name, replacement)
        if hasattr(model, "history"):
            from simple_history.utils import bulk_update_with_history

            bulk_update_with_history(
                [obj],
                model,
                fields=[field_name],
                default_change_reason="Correction orthographique IA validée",
            )
        else:
            model.objects.filter(pk=pk).update(**{field_name: replacement})
        return "done"


class Command(BaseCommand):
    help = "Prépare les corrections orthographiques, puis applique uniquement le journal relu. Aucune traduction."

    def add_arguments(self, parser):
        parser.add_argument(
            "--journal", required=True, help="Journal JSONL privé et persistant"
        )
        phases = parser.add_mutually_exclusive_group()
        phases.add_argument(
            "--apply", action="store_true", help="Appliquer les corrections du journal"
        )
        phases.add_argument(
            "--rollback",
            action="store_true",
            help="Annuler les corrections sans écraser les modifications ultérieures",
        )
        parser.add_argument(
            "--limit", type=int, help="Limiter la préparation à N champs"
        )
        parser.add_argument(
            "--model", action="append", help="Limiter à app.Model (répétable)"
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=2.1,
            help="Pause entre champs préparés, en secondes",
        )

    def handle(self, *args, **options):
        path = Path(options["journal"])
        if (options["apply"] or options["rollback"]) and not path.is_file():
            raise CommandError("Préparez le journal avant de l’appliquer.")
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(lock_fd, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CommandError(
                    "Ce journal est déjà utilisé par une autre exécution."
                )
            return self._run(**options)

    def _run(self, **options):
        if options["limit"] is not None and options["limit"] < 1:
            raise CommandError("--limit doit être positif")
        path = Path(options["journal"])
        path.parent.mkdir(parents=True, exist_ok=True)
        records = []
        if path.exists():
            with path.open() as source:
                for index, line in enumerate(source, 1):
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        raise CommandError(
                            f"Journal invalide à la ligne {index}; sauvegardez puis retirez la dernière ligne incomplète."
                        )
        prepared = {
            row["key"]: row for row in records if row.get("status") == "prepared"
        }
        started = time.monotonic()
        models = [
            model
            for model in apps.get_models()
            if editable_fields(model)
            and (not options["model"] or model._meta.label in options["model"])
        ]
        if options["model"] and set(options["model"]) - {
            model._meta.label for model in models
        }:
            raise CommandError("Modèle inconnu ou sans texte autorisé")
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "a") as stream:
            os.chmod(path, 0o600)
            if options["apply"] or options["rollback"]:
                items = [
                    row
                    for row in prepared.values()
                    if row["before"] != row["after"]
                    and (not options["model"] or row["model"] in options["model"])
                ]
                failures = 0
                for index, row in enumerate(items, 1):
                    model = apps.get_model(row["model"])
                    if row["field"] not in {
                        field.name for field in editable_fields(model)
                    }:
                        raise CommandError("Champ non autorisé dans le journal")
                    before, after = row["before"], row["after"]
                    if options["rollback"]:
                        before, after = after, before
                    result = save_field(model, row["pk"], row["field"], before, after)
                    failures += not result.startswith("done")
                    write_record(
                        stream,
                        {
                            "key": row["key"],
                            "status": "rollback" if options["rollback"] else "apply",
                            "result": result,
                        },
                    )
                    self.stdout.write(
                        f"[{index}/{len(items)}] {row['model']} #{row['pk']} · {row['field']} : {result}"
                    )
                if failures:
                    raise CommandError(
                        f"{failures} champs ignorés (conflit ou suppression). Aucun écrasement."
                    )
                return
            selections = [
                (
                    model,
                    field,
                    (
                        model.objects.exclude(**{field.name: None}).exclude(
                            **{field.name: ""}
                        )
                        if isinstance(field, (CharField, TextField))
                        else model.objects.all()
                    ),
                )
                for model in models
                for field in editable_fields(model)
            ]
            total = sum(query.count() for _, _, query in selections)
            if options["limit"]:
                total = min(total, options["limit"])
            done = changed = failed = 0
            for model, field, query in selections:
                for obj in query.order_by("pk").iterator(chunk_size=100):
                    if done >= total:
                        break
                    value = getattr(obj, field.name)
                    key = f"{model._meta.label}:{obj.pk}:{field.name}:{fingerprint(value)}"
                    done += 1
                    label = f"{model._meta.label} #{obj.pk} · {field.verbose_name}"
                    if key in prepared:
                        self.stdout.write(f"[{done}/{total}] {label} : done (journal)")
                        continue
                    self.stdout.write(
                        f"[{done}/{total}] {label} : en cours", ending="\n"
                    )
                    try:
                        protected = [
                            getattr(obj, name, "")
                            for name in (
                                "reference",
                                "numero_contrat",
                                "numero_facture",
                                "client_nom",
                                "st_name",
                                "st_rep",
                                "supplier_name",
                                "nom_client",
                            )
                        ]
                        protected = [
                            text
                            for text in protected
                            if isinstance(text, str) and 1 < len(text) <= 200
                        ]
                        after = correct_value(value, field, protected)
                        row = {
                            "key": key,
                            "status": "prepared",
                            "model": model._meta.label,
                            "pk": obj.pk,
                            "field": field.name,
                            "before": value,
                            "after": after,
                        }
                        write_record(stream, row)
                        prepared[key] = row
                        changed += after != value
                        status = (
                            "done (correction proposée)"
                            if after != value
                            else "done (inchangé)"
                        )
                    except Exception as exc:
                        failed += 1
                        status = (
                            f"erreur ({type(exc).__name__}); relancer pour réessayer"
                        )
                        write_record(
                            stream,
                            {
                                "key": key,
                                "status": "error",
                                "error": type(exc).__name__,
                            },
                        )
                    elapsed = time.monotonic() - started
                    eta = int(elapsed / done * (total - done)) if done else 0
                    self.stdout.write(
                        f"[{done}/{total} · {done/max(total,1):.0%}] {label} : {status} · reste estimé {eta//60} min {eta%60} s"
                    )
                    time.sleep(max(0, options["pause"]))
            self.stdout.write(
                f"Terminé : {done} champs, {changed} corrections proposées, {failed} erreurs. Aucune donnée modifiée. Journal : {path}"
            )
            if failed:
                raise CommandError(
                    "Des champs ont échoué; relancez avec le même journal."
                )
