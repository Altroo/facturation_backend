from os import path
from uuid import uuid4

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


def get_article_image_path(_, filename):
    """Store article images in a dedicated folder with a random name."""
    _, ext = path.splitext(filename)
    return path.join("article_images", f"{uuid4()}{ext}")


class Article(models.Model):
    # Foreign keys
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="articles",
        verbose_name="Société",
        help_text="Société propriétaire de l'article",
    )
    marque = models.ForeignKey(
        "parameter.Marque",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Marque",
        help_text="Marque de l'article",
    )
    categorie = models.ForeignKey(
        "parameter.Categorie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Catégorie",
        help_text="Catégorie de l'article",
    )
    emplacement = models.ForeignKey(
        "parameter.Emplacement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Emplacement",
        help_text="Emplacement de stockage",
    )
    unite = models.ForeignKey(
        "parameter.Unite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Unité",
        help_text="Unité de mesure (ex: pièce, kg)",
    )
    # Core fields
    reference = models.CharField(
        max_length=100,
        verbose_name="Référence",
        unique=True,
        help_text="Référence unique de l'article",
    )
    designation = models.TextField(
        verbose_name="Désignation",
        help_text="Désignation ou description courte de l'article",
    )
    photo = models.ImageField(
        upload_to=get_article_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Photo",
        help_text="Photo de l'article",
        max_length=1000,
    )

    # Pricing
    prix_achat = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Prix d'achat",
        help_text="Prix d'achat unitaire",
    )
    prix_vente = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Prix de vente",
        help_text="Prix de vente unitaire",
    )
    tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        verbose_name="TVA (%)",
        help_text="Taux de TVA appliqué (en pourcentage)",
    )

    # Type choice
    TYPE_CHOICES = [
        ("Produit", "Produit"),
        ("Service", "Service"),
    ]
    type_article = models.CharField(
        max_length=7,
        choices=TYPE_CHOICES,
        default="produit",
        verbose_name="Type d'article",
        help_text="Type : Produit ou Service",
    )

    remarque = models.TextField(
        blank=True,
        null=True,
        verbose_name="Remarque",
        help_text="Remarques internes concernant l'article",
    )

    # Metadata
    date_created = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création",
        help_text="Horodatage de la création de l'article",
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Horodatage de la dernière modification",
        db_index=True,
    )
    archived = models.BooleanField(
        default=False,
        verbose_name="Archivé",
        help_text="Indique si l'article est archivé",
        db_index=True,
    )

    history = HistoricalRecords(
        verbose_name="Historique Article",
        verbose_name_plural="Historiques Articles"
    )

    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        ordering = ("-date_created",)

    def __str__(self):
        return f"{self.reference} – {self.designation[:30]}"
