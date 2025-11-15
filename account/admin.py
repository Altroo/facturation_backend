from django import forms
from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from account.models import CustomUser, Membership
from .forms import CustomAuthShopChangeForm, CustomAuthShopCreationForm


class CustomUserAdmin(UserAdmin):
    add_form = CustomAuthShopCreationForm
    form = CustomAuthShopChangeForm
    model = CustomUser
    list_display = ("id", "email", "first_name", "last_name", "is_staff", "is_active")
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
        ("Date d'activité", {"fields": ("date_joined", "last_login")}),
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
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
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


# Account
admin.site.register(CustomUser, CustomUserAdmin)
# Membership
admin.site.register(Membership, MembershipAdmin)
