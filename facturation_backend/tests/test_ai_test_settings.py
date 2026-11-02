"""The synthetic AI profile cannot inherit production database coordinates."""

import runpy

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command


def load_profile():
    return runpy.run_module("facturation_backend.settings_ai_test")


def test_ai_profile_uses_separate_local_credentials(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "production.invalid")
    monkeypatch.setenv("POSTGRES_DB", "production")
    monkeypatch.setenv("POSTGRES_USER", "production_user")
    monkeypatch.setenv("CHAT_AI_TEST_DB_HOST", "/tmp/isolated-postgres")
    monkeypatch.setenv("CHAT_AI_TEST_DB_USER", "local_tester")
    monkeypatch.setenv("CHAT_AI_TEST_DB_PASSWORD", "test-only")
    monkeypatch.setenv("CHAT_AI_TEST_DB_PORT", "55439")
    database = load_profile()["DATABASES"]["default"]
    assert database["HOST"] == "/tmp/isolated-postgres"
    assert database["NAME"] == "chat_ai_facturation_dev"
    assert database["TEST"]["NAME"] == "test_chat_ai_facturation"
    assert database["USER"] == "local_tester"
    assert database["PASSWORD"] == "test-only"
    assert database["PORT"] == "55439"


def test_ai_profile_refuses_remote_database(monkeypatch):
    monkeypatch.setenv("CHAT_AI_TEST_DB_HOST", "production.invalid")
    with pytest.raises(ImproperlyConfigured, match="local host"):
        load_profile()


@pytest.mark.django_db
def test_synthetic_seed_refuses_normal_test_profile():
    with pytest.raises(CommandError, match="Synthetic local database only"):
        call_command("seed_ai_test_data")
