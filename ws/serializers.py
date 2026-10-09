from rest_framework import serializers

from .models import ChangelogEntry


class ChangelogEntrySerializer(serializers.ModelSerializer):
    changes_fr = serializers.SerializerMethodField()
    changes_en = serializers.SerializerMethodField()

    class Meta:
        model = ChangelogEntry
        fields = (
            "id",
            "date",
            "version",
            "title_fr",
            "title_en",
            "changes_fr",
            "changes_en",
        )

    @staticmethod
    def get_changes_fr(entry):
        return [line.strip() for line in entry.changes_fr.splitlines() if line.strip()]

    @staticmethod
    def get_changes_en(entry):
        return [line.strip() for line in entry.changes_en.splitlines() if line.strip()]
