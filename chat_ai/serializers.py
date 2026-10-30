from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({"error": "Unsupported fields."})
        return super().to_internal_value(data)


class NewConversationSerializer(StrictSerializer):
    company_id = serializers.IntegerField(min_value=1)


class MessageContextSerializer(StrictSerializer):
    interface_language = serializers.ChoiceField(choices=["fr", "en"], required=False)
    invoice_id = serializers.IntegerField(min_value=1, required=False)


class MessageRequestSerializer(StrictSerializer):
    text = serializers.CharField(max_length=4000, trim_whitespace=True)
    request_id = serializers.UUIDField()
    context = MessageContextSerializer(default=dict)


class FeedbackSerializer(StrictSerializer):
    message_id = serializers.UUIDField()
    helpful = serializers.BooleanField()


class ConfirmationSerializer(StrictSerializer):
    confirmed = serializers.BooleanField()


class RecordSelectionSerializer(StrictSerializer):
    resource = serializers.ChoiceField(
        choices=[
            "invoice",
            "quote",
            "client",
            "proforma",
            "credit_note",
            "delivery_note",
        ]
    )
    identifier = serializers.IntegerField(min_value=1)
    operation = serializers.ChoiceField(choices=["edit", "delete"])
