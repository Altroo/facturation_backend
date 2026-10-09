from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

MAINTENANCE_GROUP = "maintenance"
DEFAULT_APP_VERSION = "0.1.0"
app_version_validator = RegexValidator(
    r"^(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\Z",
    "Use a release version such as 1.2.0 (three numbers, up to six digits each).",
)


class WsMaintenanceState(models.Model):
    maintenance = models.BooleanField(default=False, verbose_name=_("Maintenance"))
    version = models.CharField(
        max_length=20,
        default=DEFAULT_APP_VERSION,
        validators=[app_version_validator],
        verbose_name=_("Version"),
        help_text=_(
            "Publish only after this frontend version is deployed and healthy."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Maintenance")
        verbose_name_plural = _("Maintenance")


class ChangelogEntry(models.Model):
    date = models.DateField(default=timezone.localdate, unique=True)
    version = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[app_version_validator],
        help_text=_("Release version. Leave empty for older, unversioned entries."),
    )
    title_fr = models.CharField(
        max_length=200, blank=True, verbose_name=_("Title — French")
    )
    title_en = models.CharField(
        max_length=200, blank=True, verbose_name=_("Title — English")
    )
    changes_fr = models.TextField(
        blank=True,
        verbose_name=_("Changes — French"),
        help_text=_("One change per line. Plain language, no HTML."),
    )
    changes_en = models.TextField(
        blank=True,
        verbose_name=_("Changes — English"),
        help_text=_("One change per line. Plain language, no HTML."),
    )
    is_published = models.BooleanField(default=False, verbose_name=_("Published"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-pk")
        verbose_name = _("Changelog entry")
        verbose_name_plural = _("Changelog")

    def __str__(self):
        return f"{self.date} — {self.title_fr or self.title_en}"

    def clean(self):
        super().clean()
        if self.is_published:
            errors = {
                field: _("Complete both languages before publishing.")
                for field in ("title_fr", "title_en", "changes_fr", "changes_en")
                if not getattr(self, field).strip()
            }
            if errors:
                raise ValidationError(errors)


def maintenance_snapshot():
    latest = WsMaintenanceState.objects.order_by("-updated_at", "-pk").first()
    return {
        "maintenance": bool(latest and latest.maintenance),
        "version": latest.version if latest else DEFAULT_APP_VERSION,
    }


@receiver(post_save, sender=WsMaintenanceState)
@receiver(post_delete, sender=WsMaintenanceState)
def broadcast_maintenance_state(sender, instance, **kwargs):
    def publish():
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            MAINTENANCE_GROUP,
            {
                "type": "receive_group_message",
                "message": {
                    "type": "MAINTENANCE",
                    **maintenance_snapshot(),
                },
            },
        )

    transaction.on_commit(publish, robust=True)
