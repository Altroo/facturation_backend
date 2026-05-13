# Generated manually for facture_avoir.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.constants


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("article", "0015_article_article_company_archived_idx"),
        ("client", "0013_alter_client_company"),
        ("company", "0010_company_uses_foreign_currency"),
        ("facture_client", "0018_alter_factureclient_total_ttc_and_more"),
        ("parameter", "0010_add_company_to_parameters"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FactureAvoir",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "remarque",
                    models.TextField(
                        blank=True,
                        help_text="Remarque ou note supplémentaire pour le document",
                        null=True,
                        verbose_name="Remarque",
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("Brouillon", "Brouillon"),
                            ("Envoyé", "Envoyé"),
                            ("Accepté", "Accepté"),
                            ("Refusé", "Refusé"),
                            ("Annulé", "Annulé"),
                            ("Expiré", "Expiré"),
                        ],
                        db_index=True,
                        default="Brouillon",
                        help_text="Statut du document (ex: Brouillon, Envoyé)",
                        max_length=10,
                        verbose_name="Statut",
                    ),
                ),
                (
                    "total_ht",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        editable=False,
                        help_text="Somme des totaux des lignes avant TVA",
                        max_digits=10,
                        verbose_name="Total HT",
                    ),
                ),
                (
                    "total_tva",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        editable=False,
                        help_text="Montant total de la TVA (calculé sur le HT après remise globale)",
                        max_digits=10,
                        verbose_name="Total TVA",
                    ),
                ),
                (
                    "total_ttc",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        editable=False,
                        help_text="Total TTC final (HT après remise + TVA sur HT après remise)",
                        max_digits=10,
                        verbose_name="Total TTC",
                    ),
                ),
                (
                    "remise_type",
                    models.CharField(
                        blank=True,
                        choices=core.constants.REMISE_TYPE_CHOICES,
                        default="",
                        help_text="Type de remise appliquée : 'Pourcentage' ou 'Fixe'",
                        max_length=12,
                        null=True,
                        verbose_name="Type de remise",
                    ),
                ),
                (
                    "remise",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        help_text="Valeur de la remise appliquée",
                        max_digits=10,
                        verbose_name="Valeur remise",
                    ),
                ),
                (
                    "total_ttc_apres_remise",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        editable=False,
                        help_text="Total TTC après application de la remise (identique à total_ttc)",
                        max_digits=10,
                        verbose_name="Total TTC après remise",
                    ),
                ),
                (
                    "devise",
                    models.CharField(
                        choices=core.constants.CURRENCY_CHOICES,
                        db_index=True,
                        default="MAD",
                        help_text="Devise utilisée pour ce document (héritée du premier article ajouté)",
                        max_length=3,
                        verbose_name="Devise",
                    ),
                ),
                (
                    "date_created",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Horodatage de la création du document",
                        verbose_name="Date de création",
                    ),
                ),
                (
                    "date_updated",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Horodatage de la dernière modification du document",
                        verbose_name="Date de mise à jour",
                    ),
                ),
                (
                    "numero_avoir",
                    models.CharField(
                        help_text="Format ex: AV-2026-0001",
                        max_length=20,
                        verbose_name="Numéro de la facture d'avoir",
                    ),
                ),
                (
                    "date_avoir",
                    models.DateField(
                        db_index=True,
                        help_text="Date d'émission de la facture d'avoir",
                        verbose_name="Date de l'avoir",
                    ),
                ),
                (
                    "motif_avoir",
                    models.CharField(
                        choices=[
                            ("retour_marchandise", "Retour marchandise"),
                            ("erreur_facturation", "Erreur de facturation"),
                            ("remise", "Remise"),
                            ("annulation", "Annulation"),
                            ("autre", "Autre"),
                        ],
                        help_text="Motif obligatoire de la facture d'avoir",
                        max_length=30,
                        verbose_name="Motif de l'avoir",
                    ),
                ),
                (
                    "numero_bon_commande_client",
                    models.CharField(
                        blank=True,
                        help_text="Référence optionnelle pour les avoirs libres",
                        max_length=50,
                        null=True,
                        verbose_name="Référence client",
                    ),
                ),
                (
                    "client",
                    models.ForeignKey(
                        help_text="Client associé au document",
                        on_delete=django.db.models.deletion.PROTECT,
                        to="client.client",
                        verbose_name="Client",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        help_text="Société propriétaire de la facture d'avoir",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="factures_avoir",
                        to="company.company",
                        verbose_name="Société",
                    ),
                ),
                (
                    "created_by_user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Utilisateur ayant créé le document",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Créé par l'utilisateur",
                    ),
                ),
                (
                    "facture_origine",
                    models.ForeignKey(
                        blank=True,
                        help_text="Facture client créditée par cet avoir",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="avoirs",
                        to="facture_client.factureclient",
                        verbose_name="Facture d'origine",
                    ),
                ),
                (
                    "mode_paiement",
                    models.ForeignKey(
                        blank=True,
                        help_text="Mode de paiement préféré pour le document",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="parameter.modepaiement",
                        verbose_name="Mode de paiement",
                    ),
                ),
            ],
            options={
                "verbose_name": "Facture d'avoir",
                "verbose_name_plural": "Factures d'avoir",
                "ordering": ("-date_created",),
                "unique_together": {("numero_avoir", "company")},
            },
        ),
        migrations.CreateModel(
            name="FactureAvoirLine",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "prix_achat",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Prix d'achat unitaire (ex: en MAD)",
                        max_digits=10,
                        verbose_name="Prix d'achat",
                    ),
                ),
                (
                    "devise_prix_achat",
                    models.CharField(
                        choices=core.constants.CURRENCY_CHOICES,
                        default="MAD",
                        help_text="Devise utilisée pour le prix d'achat",
                        max_length=3,
                        verbose_name="Devise prix d'achat",
                    ),
                ),
                (
                    "prix_vente",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Prix de vente unitaire (ex: en MAD)",
                        max_digits=10,
                        verbose_name="Prix de vente",
                    ),
                ),
                (
                    "devise_prix_vente",
                    models.CharField(
                        choices=core.constants.CURRENCY_CHOICES,
                        default="MAD",
                        help_text="Devise utilisée pour le prix de vente",
                        max_length=3,
                        verbose_name="Devise prix de vente",
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=2,
                        default=1,
                        help_text="Quantité (ex: 15,35)",
                        max_digits=10,
                        verbose_name="Quantité",
                    ),
                ),
                (
                    "remise_type",
                    models.CharField(
                        blank=True,
                        choices=core.constants.REMISE_TYPE_CHOICES,
                        default="",
                        help_text="Type de remise appliquée : 'Pourcentage' ou 'Fixe'",
                        max_length=12,
                        null=True,
                        verbose_name="Type de remise",
                    ),
                ),
                (
                    "remise",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        help_text="Valeur de la remise appliquée",
                        max_digits=10,
                        verbose_name="Valeur remise",
                    ),
                ),
                (
                    "article",
                    models.ForeignKey(
                        help_text="Article associé à cette ligne d'avoir",
                        on_delete=django.db.models.deletion.PROTECT,
                        to="article.article",
                        verbose_name="Article",
                    ),
                ),
                (
                    "facture_avoir",
                    models.ForeignKey(
                        help_text="Facture d'avoir associée à cette ligne",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lignes",
                        to="facture_avoir.factureavoir",
                        verbose_name="Facture d'avoir",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ligne de facture d'avoir",
                "verbose_name_plural": "Lignes de factures d'avoir",
            },
        ),
        migrations.AddIndex(
            model_name="factureavoir",
            index=models.Index(fields=["company", "date_avoir"], name="facture_avo_company_64ad2e_idx"),
        ),
        migrations.AddIndex(
            model_name="factureavoir",
            index=models.Index(fields=["client", "company"], name="facture_avo_client__b77ad9_idx"),
        ),
        migrations.AddIndex(
            model_name="factureavoir",
            index=models.Index(fields=["facture_origine", "company"], name="facture_avo_facture_8f09c5_idx"),
        ),
        migrations.AddIndex(
            model_name="factureavoir",
            index=models.Index(fields=["motif_avoir", "company"], name="facture_avo_motif_a_32dc49_idx"),
        ),
    ]
