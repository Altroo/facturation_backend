from django import forms
from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.contrib.auth.admin import UserAdmin

from account.models import CustomUser, Membership, Role
from company.models import Company
from .forms import CustomAuthShopChangeForm, CustomAuthShopCreationForm


class CustomUserAdmin(UserAdmin):
    add_form = CustomAuthShopCreationForm
    form = CustomAuthShopChangeForm
    model = CustomUser
    readonly_fields = ("date_updated",)
    list_display = (
        "id",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "date_joined",
        "date_updated",
    )
    list_filter = ("is_staff", "is_active")
    date_hierarchy = "date_joined"
    fieldsets = (
        (
            "Profile",
            {
                "fields": (
                    "email",
                    "password",
                    "first_name",
                    "last_name",
                    "gender",
                    "avatar",
                    "avatar_cropped",
                    "password_reset_code",
                )
            },
        ),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Date d'activité", {"fields": ("date_joined", "date_updated", "last_login")}),
    )
    # add fields to the admin panel creation model
    add_fieldsets = (
        (
            "Profile",
            {
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "gender",
                )
            },
        ),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    search_fields = ("email",)
    ordering = ("-id",)


class MembershipAdminForm(forms.ModelForm):
    company = forms.ModelChoiceField(
        queryset=Company.objects.all(),
        required=False,
        label="Company",
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        required=False,
        label="Role",
    )

    class Meta:
        model = Membership
        fields = "__all__"


class MembershipAdmin(ModelAdmin):
    form = MembershipAdminForm
    list_display = ("id", "user", "company", "role")
    list_filter = ("role", "company")
    search_fields = ("user__email", "company__raison_sociale", "role__name")


class RoleAdmin(ModelAdmin):
    list_display = ("id", "name", "is_admin")
    list_filter = ("is_admin",)
    search_fields = ("name",)
    ordering = ("-is_admin", "name")


# Account
admin.site.register(CustomUser, CustomUserAdmin)
# Role
admin.site.register(Role, RoleAdmin)
# Membership
admin.site.register(Membership, MembershipAdmin)


# Historical Model Admins (Read-only)
class HistoricalCustomUserAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical CustomUser records."""
    
    list_display = (
        "history_id",
        "id",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "history_type",
        "history_date",
        "history_user",
    )
    
    list_filter = (
        "history_type",
        "history_date",
        "is_active",
        "is_staff",
    )
    
    search_fields = (
        "email",
        "first_name",
        "last_name",
    )
    
    readonly_fields = [field.name for field in CustomUser._meta.get_fields() if hasattr(field, 'name') and not field.many_to_many and not field.one_to_many] + [
        "history_id",
        "history_date",
        "history_change_reason",
        "history_type",
        "history_user",
    ]
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


class HistoricalMembershipAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Membership records."""
    
    list_display = (
        "history_id",
        "id",
        "user",
        "company",
        "role",
        "history_type",
        "history_date",
        "history_user",
    )
    
    list_filter = (
        "history_type",
        "history_date",
        "role",
    )
    
    search_fields = (
        "user__email",
        "company__raison_sociale",
    )
    
    readonly_fields = [field.name for field in Membership._meta.get_fields() if hasattr(field, 'name') and not field.many_to_many and not field.one_to_many] + [
        "history_id",
        "history_date",
        "history_change_reason",
        "history_type",
        "history_user",
    ]
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(CustomUser.history.model, HistoricalCustomUserAdmin)
admin.site.register(Membership.history.model, HistoricalMembershipAdmin)
