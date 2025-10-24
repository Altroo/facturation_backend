from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .managers import CustomUserManager


class CustomUser(AbstractBaseUser, PermissionsMixin):
    # Password (hidden)
    email = models.EmailField(_('email address'), unique=True)
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    # permissions
    is_staff = models.BooleanField(_('staff status'),
                                   default=False,
                                   help_text=_('Designates whether the user can log into this admin site.'), )
    is_active = models.BooleanField(_('active'),
                                    default=True,
                                    help_text=_(
                                        'Designates whether this user should be treated as active. '
                                        'Unselect this instead of deleting accounts.'
                                    ), )
    # DATES
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    # Codes
    activation_code = models.IntegerField(verbose_name='Account Verification Code', blank=True, null=True)
    password_reset_code = models.IntegerField(verbose_name='Password Reset Code', blank=True, null=True)
    # Task ids for Codes
    task_id_activation = models.CharField(verbose_name='Task ID activation',
                                          max_length=40, default=None, null=True, blank=True)
    task_id_password_reset = models.CharField(verbose_name='Task ID password reset',
                                              max_length=40, default=None, null=True, blank=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return '{}'.format(self.email)

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ('date_joined',)
