from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("facture_avoir", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="factureavoir",
            new_name="facture_avo_company_64298c_idx",
            old_name="facture_avo_company_64ad2e_idx",
        ),
        migrations.RenameIndex(
            model_name="factureavoir",
            new_name="facture_avo_client__fd4f9b_idx",
            old_name="facture_avo_client__b77ad9_idx",
        ),
        migrations.RenameIndex(
            model_name="factureavoir",
            new_name="facture_avo_facture_428ad9_idx",
            old_name="facture_avo_facture_8f09c5_idx",
        ),
        migrations.RenameIndex(
            model_name="factureavoir",
            new_name="facture_avo_motif_a_4a27f8_idx",
            old_name="facture_avo_motif_a_32dc49_idx",
        ),
    ]
