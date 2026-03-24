from django.contrib import admin

from ws.models import WsMaintenanceState


class WsMaintenanceStateAdmin(admin.ModelAdmin):
    list_display = ("maintenance", "updated_at")


admin.site.register(WsMaintenanceState, WsMaintenanceStateAdmin)
