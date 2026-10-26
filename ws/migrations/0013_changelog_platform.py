from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("ws", "0012_handled_errors_release_3_8_6")]

    operations = [
        # The default classifies existing history as Web without changing its text.
        migrations.AddField(
            model_name="changelogentry",
            name="platform",
            field=models.CharField(
                choices=[("web", "Web"), ("mobile", "Mobile"), ("both", "Web and Mobile")],
                default="web",
                help_text="Show this entry on Web, Mobile, or both applications.",
                max_length=6,
                verbose_name="Platform",
            ),
        ),
        migrations.AlterField(
            model_name="changelogentry",
            name="date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
        migrations.AddConstraint(
            model_name="changelogentry",
            constraint=models.UniqueConstraint(
                fields=("date", "platform"), name="ws_changelog_date_platform_unique"
            ),
        ),
    ]
