import uuid
from django.conf import settings
from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey("company.Company", on_delete=models.CASCADE)
    application = models.CharField(max_length=32, default="facturation", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    references = models.JSONField(default=dict)
    authorization_stamp = models.CharField(max_length=64)

    class Meta:
        indexes = [models.Index(fields=["user", "company", "-updated_at"])]


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, related_name="messages", on_delete=models.CASCADE)
    role = models.CharField(max_length=12, choices=[("user", "user"), ("assistant", "assistant")])
    text = models.TextField(blank=True)
    # Store the request for replay, NEVER a snapshot of private tool results.
    action = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    request_id = models.UUIDField(default=uuid.uuid4)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["conversation", "request_id", "role"], name="chat_ai_unique_request_role")]


class KnowledgeDocument(models.Model):
    document_id = models.CharField(primary_key=True, max_length=80)
    application_id = models.CharField(max_length=32, default="facturation")
    document_version = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    content = models.TextField()
    localized_content = models.JSONField(default=dict, blank=True)
    keywords = models.JSONField(default=list)
    category = models.CharField(max_length=40)
    sensitivity = models.CharField(max_length=20, default="member")
    required_capabilities = models.JSONField(default=list)
    tenant_scope = models.ForeignKey("company.Company", null=True, blank=True, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)


class AuditEvent(models.Model):
    instruction_id = models.UUIDField(null=True, db_index=True)
    actor_id = models.PositiveBigIntegerField(null=True)
    actor_label = models.CharField(max_length=254, blank=True)
    resource = models.CharField(max_length=32, blank=True)
    record_id = models.PositiveBigIntegerField(null=True)
    changed_fields = models.JSONField(default=list)
    source = models.CharField(max_length=32, default="chat_ai_assistant")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    company_id = models.PositiveBigIntegerField(null=True)
    application = models.CharField(max_length=32, default="facturation")
    tool = models.CharField(max_length=64)
    outcome = models.CharField(max_length=40)
    correlation_id = models.UUIDField()
    model_version = models.CharField(max_length=120)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class InferenceLease(models.Model):
    name = models.CharField(primary_key=True, max_length=40)
    owner = models.UUIDField(null=True)
    expires_at = models.DateTimeField(null=True)


class Feedback(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    helpful = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "user"], name="chat_ai_unique_feedback")]


class PendingAction(models.Model):
    instruction_id = models.UUIDField(null=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey("company.Company", on_delete=models.CASCADE)
    resource = models.CharField(max_length=20)
    record_id = models.PositiveBigIntegerField()
    operation = models.CharField(max_length=12)
    changes = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
