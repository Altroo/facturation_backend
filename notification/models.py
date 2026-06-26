from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from django.conf import settings


class NotificationPreference(models.Model):
    """User-specific notification preferences."""

    REMINDER_CHOICES = [
        (0, _("Au moment de l'événement")),
        (1, _("1 jour avant")),
        (3, _("3 jours avant")),
        (7, _("7 jours avant")),
        (14, _("14 jours avant")),
        (30, _("30 jours avant")),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
        verbose_name=_("Utilisateur"),
    )
    notify_overdue_invoice = models.BooleanField(
        default=True,
        verbose_name=_("Notifier les factures en retard"),
    )
    notify_expiring_quote = models.BooleanField(
        default=True,
        verbose_name=_("Notifier les devis expirants"),
    )
    notify_uninvoiced_bdl = models.BooleanField(
        default=True,
        verbose_name=_("Notifier les BLs non facturés"),
    )
    notify_document_created = models.BooleanField(
        default=True,
        verbose_name=_("Notifier la création de documents"),
    )
    quote_expiry_days = models.IntegerField(
        choices=REMINDER_CHOICES,
        default=7,
        verbose_name=_("Alerter X jours avant expiration devis"),
    )
    date_created = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Date création")
    )
    date_updated = models.DateTimeField(
        auto_now=True, verbose_name=_("Date modification")
    )
    history = HistoricalRecords(
        verbose_name=_("Historique Préférence Notification"),
        verbose_name_plural=_("Historiques Préférences Notifications"),
    )

    class Meta:
        verbose_name = _("Préférence de notification")
        verbose_name_plural = _("Préférences de notification")

    def __str__(self) -> str:
        return f"Notifications — {self.user.email}"


class Notification(models.Model):
    """A notification sent to a user about a facturation event."""

    NOTIFICATION_TYPES = [
        ("overdue_invoice", _("Facture en retard")),
        ("expiring_quote", _("Devis expirant")),
        ("uninvoiced_bdl", _("BL non facturé")),
        ("status_change", _("Changement de statut")),
        ("document_created", _("Document créé")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("Utilisateur"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Titre"))
    message = models.TextField(verbose_name=_("Message"))
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES,
        verbose_name=_("Type"),
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("ID de l'objet lié"),
    )
    is_read = models.BooleanField(default=False, verbose_name=_("Lu"))
    date_created = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Date création"), db_index=True
    )
    history = HistoricalRecords(
        verbose_name=_("Historique Notification"),
        verbose_name_plural=_("Historiques Notifications"),
    )

    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ("-date_created",)

    def __str__(self) -> str:
        return f"{self.title} — {self.user.email}"
