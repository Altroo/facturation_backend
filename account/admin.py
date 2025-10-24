from django.contrib.auth.admin import UserAdmin
from django.contrib import admin
from .forms import CustomAuthShopCreationForm, CustomAuthShopChangeForm
from account.models import CustomUser


class CustomUserAdmin(UserAdmin):
    add_form = CustomAuthShopCreationForm
    form = CustomAuthShopChangeForm
    model = CustomUser
    list_display = ('id', 'email', 'first_name', 'last_name',
                    'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active')
    date_hierarchy = 'date_joined'
    fieldsets = (
        ('Profile', {'fields': ('email', 'password', 'first_name', 'last_name', 'gender', 'avatar', 'avatar_thumbnail',
                                'password_reset_code')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ("Date d'activité", {'fields': ('date_joined', 'last_login')}),
    )
    # add fields to the admin panel creation model
    add_fieldsets = (
        ('Profile', {'fields': ('email', 'password1', 'password2', 'first_name', 'last_name',
                                'activation_code', 'password_reset_code')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    search_fields = ('email',)
    ordering = ('-id',)


# Account
admin.site.register(CustomUser, CustomUserAdmin)
