# Generated manually

import django.db.models.deletion
from django.db import migrations, models


def set_default_company(apps, schema_editor):
    """
    Assign existing parameter rows to the first Company found (if any).
    This is a data migration for backwards-compatibility only.
    In production the table is expected to be empty or manually handled.
    """
    Company = apps.get_model("company", "Company")
    first_company = Company.objects.order_by("pk").first()
    if first_company is None:
        return  # nothing to backfill

    model_names = [
        "Ville",
        "ModePaiement",
        "Marque",
        "Categorie",
        "Unite",
        "Emplacement",
        "LivrePar",
    ]
    for model_name in model_names:
        Model = apps.get_model("parameter", model_name)
        Model.objects.filter(company__isnull=True).update(company=first_company)


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0010_company_uses_foreign_currency"),
        ("parameter", "0009_alter_historicalcategorie_options_and_more"),
    ]

    operations = [
        # Step 1: Add nullable company FK to each model
        migrations.AddField(
            model_name="ville",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="villes",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette ville",
            ),
        ),
        migrations.AddField(
            model_name="modepaiement",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="modes_paiement",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de ce mode de paiement",
            ),
        ),
        migrations.AddField(
            model_name="marque",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="marques",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette marque",
            ),
        ),
        migrations.AddField(
            model_name="categorie",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="categories",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette catégorie",
            ),
        ),
        migrations.AddField(
            model_name="unite",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unites",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette unité",
            ),
        ),
        migrations.AddField(
            model_name="emplacement",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="emplacements",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cet emplacement",
            ),
        ),
        migrations.AddField(
            model_name="livrepar",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="livres_par",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de ce livreur",
            ),
        ),
        # Historical models
        migrations.AddField(
            model_name="historicalville",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Société propriétaire de cette ville",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="company.company",
                verbose_name="Société",
            ),
        ),
        migrations.AddField(
            model_name="historicalmodepaiement",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Société propriétaire de ce mode de paiement",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="company.company",
                verbose_name="Société",
            ),
        ),
        migrations.AddField(
            model_name="historicalmarque",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Société propriétaire de cette marque",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="company.company",
                verbose_name="Société",
            ),
        ),
        migrations.AddField(
            model_name="historicalcategorie",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Société propriétaire de cette catégorie",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="company.company",
                verbose_name="Société",
            ),
        ),
        migrations.AddField(
            model_name="historicalunite",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Société propriétaire de cette unité",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="company.company",
                verbose_name="Société",
            ),
        ),
        migrations.AddField(
            model_name="historicalemplacement",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Société propriétaire de cet emplacement",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="company.company",
                verbose_name="Société",
            ),
        ),
        migrations.AddField(
            model_name="historicallivrepar",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Société propriétaire de ce livreur",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="company.company",
                verbose_name="Société",
            ),
        ),
        # Step 2: Backfill existing rows
        migrations.RunPython(set_default_company, migrations.RunPython.noop),
        # Step 3: Remove unique constraint on nom (all 7 models)
        migrations.AlterField(
            model_name="ville",
            name="nom",
            field=models.CharField(
                help_text="Nom de la ville",
                max_length=100,
                verbose_name="Nom de la ville",
            ),
        ),
        migrations.AlterField(
            model_name="modepaiement",
            name="nom",
            field=models.CharField(
                help_text="Nom du mode de paiement (ex: Espèces, Virement)",
                max_length=255,
                verbose_name="Nom du mode de paiement",
            ),
        ),
        migrations.AlterField(
            model_name="marque",
            name="nom",
            field=models.CharField(
                help_text="Nom de la marque",
                max_length=255,
                verbose_name="Nom de la marque",
            ),
        ),
        migrations.AlterField(
            model_name="categorie",
            name="nom",
            field=models.CharField(
                help_text="Nom de la catégorie",
                max_length=255,
                verbose_name="Nom de la catégorie",
            ),
        ),
        migrations.AlterField(
            model_name="unite",
            name="nom",
            field=models.CharField(
                help_text="Nom de l'unité (ex: pièce, kg)",
                max_length=255,
                verbose_name="Nom de l'unité",
            ),
        ),
        migrations.AlterField(
            model_name="emplacement",
            name="nom",
            field=models.CharField(
                help_text="Nom de l'emplacement (ex: Entrepôt A)",
                max_length=255,
                verbose_name="Nom de l'emplacement",
            ),
        ),
        migrations.AlterField(
            model_name="livrepar",
            name="nom",
            field=models.CharField(
                help_text="Nom du livreur",
                max_length=255,
                verbose_name="Nom du livreur",
            ),
        ),
        # Step 4: Make company non-nullable
        migrations.AlterField(
            model_name="ville",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="villes",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette ville",
            ),
        ),
        migrations.AlterField(
            model_name="modepaiement",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="modes_paiement",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de ce mode de paiement",
            ),
        ),
        migrations.AlterField(
            model_name="marque",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="marques",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette marque",
            ),
        ),
        migrations.AlterField(
            model_name="categorie",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="categories",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette catégorie",
            ),
        ),
        migrations.AlterField(
            model_name="unite",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="unites",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cette unité",
            ),
        ),
        migrations.AlterField(
            model_name="emplacement",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="emplacements",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de cet emplacement",
            ),
        ),
        migrations.AlterField(
            model_name="livrepar",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="livres_par",
                to="company.company",
                verbose_name="Société",
                help_text="Société propriétaire de ce livreur",
            ),
        ),
        # Step 5: Add unique constraints (company, nom)
        migrations.AddConstraint(
            model_name="ville",
            constraint=models.UniqueConstraint(
                fields=("company", "nom"),
                name="unique_ville_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="modepaiement",
            constraint=models.UniqueConstraint(
                fields=("company", "nom"),
                name="unique_mode_paiement_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="marque",
            constraint=models.UniqueConstraint(
                fields=("company", "nom"),
                name="unique_marque_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="categorie",
            constraint=models.UniqueConstraint(
                fields=("company", "nom"),
                name="unique_categorie_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="unite",
            constraint=models.UniqueConstraint(
                fields=("company", "nom"),
                name="unique_unite_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="emplacement",
            constraint=models.UniqueConstraint(
                fields=("company", "nom"),
                name="unique_emplacement_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="livrepar",
            constraint=models.UniqueConstraint(
                fields=("company", "nom"),
                name="unique_livre_par_per_company",
            ),
        ),
        # Step 6: Update historical model fields (nom + company)
        migrations.AlterField(
            model_name="historicalville",
            name="nom",
            field=models.CharField(
                help_text="Nom de la ville",
                max_length=100,
                verbose_name="Nom de la ville",
            ),
        ),
        migrations.AlterField(
            model_name="historicalmodepaiement",
            name="nom",
            field=models.CharField(
                help_text="Nom du mode de paiement (ex: Espèces, Virement)",
                max_length=255,
                verbose_name="Nom du mode de paiement",
            ),
        ),
        migrations.AlterField(
            model_name="historicalmarque",
            name="nom",
            field=models.CharField(
                help_text="Nom de la marque",
                max_length=255,
                verbose_name="Nom de la marque",
            ),
        ),
        migrations.AlterField(
            model_name="historicalcategorie",
            name="nom",
            field=models.CharField(
                help_text="Nom de la catégorie",
                max_length=255,
                verbose_name="Nom de la catégorie",
            ),
        ),
        migrations.AlterField(
            model_name="historicalunite",
            name="nom",
            field=models.CharField(
                help_text="Nom de l'unité (ex: pièce, kg)",
                max_length=255,
                verbose_name="Nom de l'unité",
            ),
        ),
        migrations.AlterField(
            model_name="historicalemplacement",
            name="nom",
            field=models.CharField(
                help_text="Nom de l'emplacement (ex: Entrepôt A)",
                max_length=255,
                verbose_name="Nom de l'emplacement",
            ),
        ),
        migrations.AlterField(
            model_name="historicallivrepar",
            name="nom",
            field=models.CharField(
                help_text="Nom du livreur",
                max_length=255,
                verbose_name="Nom du livreur",
            ),
        ),
    ]
