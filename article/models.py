from os import path
from uuid import uuid4

from django.db import models
from django.utils import timezone


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
    )
    marque = models.ForeignKey(
        "parameter.Marque",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Marque",
    )
    categorie = models.ForeignKey(
        "parameter.Categorie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Catégorie",
    )
    emplacement = models.ForeignKey(
        "parameter.Emplacement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Emplacement",
    )
    unite = models.ForeignKey(
        "parameter.Unite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="Unité",
    )
    # Core fields
    reference = models.CharField(
        max_length=100,
        verbose_name="Référence",
        unique=True,
    )
    designation = models.TextField(
        verbose_name="Désignation",
    )
    photo = models.ImageField(
        upload_to=get_article_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Photo",
        max_length=1000,
    )

    # Pricing
    prix_achat = models.PositiveIntegerField(
        verbose_name="Prix d'achat",
        default=0,
    )
    prix_vente = models.PositiveIntegerField(
        verbose_name="Prix de vente",
        default=0,
    )
    tva = models.PositiveIntegerField(
        default=20,
        verbose_name="TVA (%)",
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
    )

    remarque = models.TextField(
        blank=True,
        null=True,
        verbose_name="Remarque",
    )

    # Metadata
    date_created = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création",
        db_index=True,
    )
    archived = models.BooleanField(
        default=False,
        verbose_name="Archivé",
        db_index=True,
    )

    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        ordering = ("-date_created",)

    def __str__(self):
        return f"{self.reference} – {self.designation[:30]}"
