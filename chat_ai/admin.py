from django.contrib import admin
from .models import AuditEvent

@admin.register(AuditEvent)
class ChatAIAuditAdmin(admin.ModelAdmin):
    list_display=('created_at','actor_id','actor_label','company_id','tool','resource','record_id','outcome','correlation_id','instruction_id')
    list_filter=('tool','outcome','application')
    search_fields=('actor_label',)
    readonly_fields=tuple(field.name for field in AuditEvent._meta.fields)
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
    def has_view_permission(self,request,obj=None):return request.user.is_active and request.user.is_superuser
