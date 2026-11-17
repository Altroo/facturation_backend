"""One source contract for saved-content preparation and PDF lookups."""

import hashlib
import json
import logging
import re
from dataclasses import dataclass

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import PdfTextTranslation

logger = logging.getLogger(__name__)
LANGUAGES = ("fr", "en", "nl")
ENGINE_REVISION = 2
TEXT_FIELDS = ("remarque", "termes_paiement", "libelle", "conditions_paiement")
SOURCE_MODELS = {
    "article.Article": (
        "designation",
        "reference",
        "marque_id",
        "unite_id",
        "company_id",
    ),
    "parameter.Unite": ("nom", "company_id"),
    "parameter.ModePaiement": ("nom", "company_id"),
    "devi.Devi": ("remarque", "client_id", "company_id"),
    "facture_client.FactureClient": (
        "remarque",
        "termes_paiement",
        "client_id",
        "company_id",
    ),
    "facture_proforma.FactureProForma": (
        "remarque",
        "termes_paiement",
        "client_id",
        "company_id",
    ),
    "facture_avoir.FactureAvoir": (
        "remarque",
        "motif_avoir",
        "client_id",
        "company_id",
    ),
    "bon_de_livraison.BonDeLivraison": ("remarque", "client_id", "company_id"),
    "reglement.Reglement": ("libelle", "mode_reglement_id", "facture_client_id"),
}
DEPENDENCY_MODELS = {
    "company.Company": ("raison_sociale",),
    "client.Client": ("raison_sociale", "nom", "prenom"),
    "parameter.Marque": ("nom",),
}


@dataclass(frozen=True)
class TextSource:
    text: str
    protected_terms: tuple[str, ...]

    @property
    def fingerprint(self):
        payload = json.dumps(
            [1, self.text, self.protected_terms],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def source(value, protected=()):
    if not isinstance(value, str) or not value.strip():
        return None
    # Irrelevant document names must not prevent reuse of an article translation.
    relevant = {
        term
        for term in protected
        if isinstance(term, str)
        and 1 < len(term) <= 200
        and re.search(rf"(?<!\w){re.escape(term)}(?!\w)", value, re.IGNORECASE)
    }
    terms = tuple(sorted(relevant, key=lambda term: (term.casefold(), term)))
    return TextSource(value, terms)


def company_for(instance):
    company = getattr(instance, "company", None)
    invoice = getattr(instance, "facture_client", None)
    return company or (invoice.company if invoice else None)


def own_sources(instance, company):
    protected = [company.raison_sociale]
    client = getattr(instance, "client", None)
    if client is None and getattr(instance, "facture_client", None):
        client = instance.facture_client.client
    if client:
        protected.extend(
            getattr(client, key, "") for key in ("raison_sociale", "nom", "prenom")
        )
    label = getattr(getattr(instance, "_meta", None), "label", "")
    values = [getattr(instance, key, "") for key in TEXT_FIELDS]
    if label == "article.Article":
        protected.extend(
            [instance.reference, instance.marque.nom if instance.marque else ""]
        )
        values = [instance.designation]
    if label in ("parameter.Unite", "parameter.ModePaiement"):
        values = [instance.nom]
    if hasattr(instance, "get_motif_avoir_display"):
        values.append(str(instance.get_motif_avoir_display()))
    result = [spec for value in values if (spec := source(value, protected))]
    if label == "article.Article" and instance.unite:
        result.extend(own_sources(instance.unite, company))
    payment = getattr(instance, "mode_reglement", None)
    if payment:
        result.extend(own_sources(payment, company))
    return result


def pdf_sources(document, company):
    result = own_sources(document, company)
    lines = getattr(document, "lignes", None)
    if lines is not None:
        for line in lines.select_related("article__marque", "article__unite").all():
            if line.article:
                result.extend(own_sources(line.article, company))
    return list({spec.fingerprint: spec for spec in result}.values())


def dispatch_pending():
    from .tasks import translate_pending_pdf_texts

    try:
        translate_pending_pdf_texts.delay()
    except Exception:
        # The rows remain durable. Beat also drains them after broker recovery.
        logger.exception("Could not dispatch PDF translations; pending rows retained")


def ensure_sources(
    company_id, sources, languages=LANGUAGES, *, dispatch=True, priority=10
):
    sources = {spec.fingerprint: spec for spec in sources}
    if not sources:
        return
    PdfTextTranslation.objects.bulk_create(
        [
            PdfTextTranslation(
                company_id=company_id,
                fingerprint=key,
                source_text=spec.text,
                protected_terms=list(spec.protected_terms),
                language=language,
                priority=priority,
            )
            for key, spec in sources.items()
            for language in languages
        ],
        ignore_conflicts=True,
    )
    # A ready value from an older engine is never silently reused. Keep the
    # previous text for recovery, but prepare a current validated result.
    stale = PdfTextTranslation.objects.filter(
        company_id=company_id,
        fingerprint__in=sources,
        language__in=languages,
        engine_revision__lt=ENGINE_REVISION,
    )
    stale.update(
        status="pending",
        engine_revision=ENGINE_REVISION,
        attempts=0,
        available_at=timezone.now(),
        last_error="",
        lease_until=None,
        lease_token=None,
    )
    PdfTextTranslation.objects.filter(
        company_id=company_id,
        fingerprint__in=sources,
        language__in=languages,
        status="pending",
        priority__gt=priority,
    ).update(priority=priority)
    if dispatch:
        transaction.on_commit(dispatch_pending, robust=True)


def prepare_instance(instance):
    company = company_for(instance)
    if company:
        ensure_sources(company.pk, own_sources(instance, company))


def load_pdf_translations(document, company, language):
    from .exceptions import PdfTranslationPending, PdfTranslationFailed

    specs = pdf_sources(document, company)
    if not specs:
        return {}
    rows = {
        row.fingerprint: row
        for row in PdfTextTranslation.objects.filter(
            company=company,
            language=language,
            fingerprint__in=[spec.fingerprint for spec in specs],
        )
    }
    missing = [spec for spec in specs if spec.fingerprint not in rows]
    if missing:
        ensure_sources(company.pk, missing, [language], priority=0)
    outdated = [
        spec
        for spec in specs
        if spec.fingerprint in rows
        and rows[spec.fingerprint].engine_revision < ENGINE_REVISION
    ]
    if outdated:
        ensure_sources(company.pk, outdated, [language], priority=0)
        raise PdfTranslationPending()
    if any(row.status == "failed" for row in rows.values()):
        raise PdfTranslationFailed()
    if missing or any(row.status != "ready" for row in rows.values()):
        promoted = PdfTextTranslation.objects.filter(
            company=company,
            language=language,
            pk__in=[row.pk for row in rows.values() if row.status == "pending"],
            priority__gt=0,
        ).update(priority=0)
        # An explicitly requested PDF can use the foreground quota reserved by
        # the shared gateway even when the bulk backfill is deferred.
        if promoted:
            PdfTextTranslation.objects.filter(
                company=company,
                language=language,
                status="pending",
                priority=0,
                last_error="ai_rate_limited",
                fingerprint__in=[spec.fingerprint for spec in specs],
            ).update(available_at=timezone.now(), last_error="")
        if promoted and not missing:
            transaction.on_commit(dispatch_pending, robust=True)
        if not promoted:
            waits = [
                (row.available_at - timezone.now()).total_seconds()
                for row in rows.values()
                if row.status == "pending" and row.last_error == "ai_rate_limited"
            ]
            if waits and min(waits) > 10:
                from .exceptions import PdfTranslationDeferred

                raise PdfTranslationDeferred(wait=min(waits))
        raise PdfTranslationPending()
    return {spec.text: rows[spec.fingerprint].translated_text for spec in specs}


def translation_enabled():
    return getattr(settings, "AI_PDF_TRANSLATION_ENABLED", False)


def source_model(label):
    return apps.get_model(label)


def validate_saved_translation(row, translated):
    """Defence in depth before a model response becomes a reusable PDF value."""
    from .exceptions import InvalidModelResponse
    from .offline_translation import protected_segments

    if not isinstance(translated, str) or not translated.strip():
        raise InvalidModelResponse()
    if re.findall(r"\r\n|\r|\n", row.source_text) != re.findall(
        r"\r\n|\r|\n", translated
    ):
        raise InvalidModelResponse("La traduction a modifié les retours à la ligne.")
    marker = r"(?m)^[ \t]*(?:(?:[•●▪◦‣⁃][ \t]*|[-*+][ \t]+|\d+[.)][ \t]+))"
    if re.findall(marker, row.source_text) != re.findall(marker, translated):
        raise InvalidModelResponse("La traduction a modifié la liste.")
    if [
        value
        for literal, value in protected_segments(row.source_text, row.protected_terms)
        if literal
    ] != [
        value
        for literal, value in protected_segments(translated, row.protected_terms)
        if literal
    ]:
        raise InvalidModelResponse("La traduction a modifié une valeur protégée.")
