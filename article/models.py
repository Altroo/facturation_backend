from os import path
from uuid import uuid4

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from core.constants import CURRENCY_CHOICES


def get_article_image_path(_, filename):
    """Store article images in a dedicated folder with a random name."""
    _, ext = path.splitext(filename)
    return path.join("article_images", f"{uuid4()}{ext}")


class Article(models.Model):
    # Foreign keys
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de l'article"),
    )
    marque = models.ForeignKey(
        "parameter.Marque",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("Marque"),
        help_text=_("Marque de l'article"),
    )
    categorie = models.ForeignKey(
        "parameter.Categorie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("Catégorie"),
        help_text=_("Catégorie de l'article"),
    )
    emplacement = models.ForeignKey(
        "parameter.Emplacement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("Emplacement"),
        help_text=_("Emplacement de stockage"),
    )
    unite = models.ForeignKey(
        "parameter.Unite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("Unité"),
        help_text=_("Unité de mesure (ex: pièce, kg)"),
    )
    # Core fields
    reference = models.CharField(
        max_length=100,
        verbose_name=_("Référence"),
        help_text=_("Référence unique de l'article par société"),
    )
    designation = models.TextField(
        verbose_name=_("Désignation"),
        help_text=_("Désignation ou description courte de l'article"),
    )
    photo = models.ImageField(
        upload_to=get_article_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Photo"),
        help_text=_("Photo de l'article"),
        max_length=1000,
    )

    # Pricing
    prix_achat = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_("Prix d'achat"),
        help_text=_("Prix d'achat unitaire"),
    )
    devise_prix_achat = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="MAD",
        verbose_name=_("Devise prix d'achat"),
        help_text=_("Devise utilisée pour le prix d'achat"),
    )
    prix_vente = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name=_("Prix de vente"),
        help_text=_("Prix de vente unitaire"),
    )
    devise_prix_vente = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="MAD",
        verbose_name=_("Devise prix de vente"),
        help_text=_("Devise utilisée pour le prix de vente"),
    )
    tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        verbose_name=_("TVA (%)"),
        help_text=_("Taux de TVA appliqué (en pourcentage)"),
    )

    # Type choice
    TYPE_CHOICES = [
        ("Produit", _("Produit")),
        ("Service", _("Service")),
    ]
    type_article = models.CharField(
        max_length=7,
        choices=TYPE_CHOICES,
        default="produit",
        verbose_name=_("Type d'article"),
        help_text=_("Type : Produit ou Service"),
    )

    remarque = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Remarque"),
        help_text=_("Remarques internes concernant l'article"),
    )

    # Metadata
    date_created = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date de création"),
        help_text=_("Horodatage de la création de l'article"),
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date de modification"),
        help_text=_("Horodatage de la dernière modification"),
        db_index=True,
    )
    archived = models.BooleanField(
        default=False,
        verbose_name=_("Archivé"),
        help_text=_("Indique si l'article est archivé"),
        db_index=True,
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Article"), verbose_name_plural=_("Historiques Articles")
    )

    class Meta:
        verbose_name = _("Article")
        verbose_name_plural = _("Articles")
        ordering = ("-date_created",)
        unique_together = [("reference", "company")]
        indexes = [
            models.Index(
                fields=["company", "archived"], name="article_company_archived_idx"
            ),
        ]

    def __str__(self):
        return f"{self.reference} – {self.designation[:30]}"
