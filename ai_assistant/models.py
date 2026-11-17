from django.db import models
from django.utils import timezone


class PdfTextTranslation(models.Model):
    """Durable, company-scoped translations of an exact source text snapshot."""

    company = models.ForeignKey("company.Company", on_delete=models.CASCADE)
    fingerprint = models.CharField(max_length=64)
    source_text = models.TextField()
    protected_terms = models.JSONField(default=list)
    language = models.CharField(
        max_length=2, choices=[(v, v) for v in ("fr", "en", "nl")]
    )
    translated_text = models.TextField(blank=True)
    engine_revision = models.PositiveSmallIntegerField(default=2, db_default=1)
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[(v, v) for v in ("pending", "processing", "ready", "failed")],
    )
    attempts = models.PositiveIntegerField(default=0)
    priority = models.PositiveSmallIntegerField(default=10)
    available_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    last_error = models.CharField(max_length=80, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "fingerprint", "language"],
                name="unique_pdf_text_translation",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "available_at"],
                name="pdf_translation_pending_idx",
            )
        ]
