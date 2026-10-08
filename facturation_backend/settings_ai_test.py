"""Isolated local database: never inherit production DB coordinates."""
from .settings_test import *  # noqa
DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':'chat_ai_facturation_dev','USER':'altroo','HOST':'localhost','PORT':'5432','TEST':{'NAME':'test_chat_ai_facturation'}}}
CHAT_AI_ASSISTANT_ENABLED=True
ALLOWED_HOSTS=['localhost','127.0.0.1','testserver']
PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']
CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}}
