"""Guard against serving old admin CSS with a newer Django template version."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.storage import storages
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from whitenoise.storage import CompressedManifestStaticFilesStorage


@pytest.fixture
def collected_static(tmp_path):
    with override_settings(STATIC_ROOT=tmp_path / "staticfiles", DEBUG=False):
        call_command("collectstatic", interactive=False, verbosity=0)
        yield Path(settings.STATIC_ROOT)


def test_static_storage_uses_hashed_urls_without_changing_upload_storage():
    assert isinstance(storages["staticfiles"], CompressedManifestStaticFilesStorage)
    assert settings.STORAGES["default"]["BACKEND"] == (
        "django.core.files.storage.FileSystemStorage"
    )
    assert Path(settings.STATIC_ROOT).name == "staticfiles"


def test_collected_admin_css_matches_installed_django(collected_static):
    for name in ("base.css", "forms.css", "nav_sidebar.css", "responsive.css"):
        relative = f"admin/css/{name}"
        source = Path(finders.find(relative)).read_bytes()
        assert (collected_static / relative).read_bytes() == source
        url = staticfiles_storage.url(relative)
        assert url != f"/static/{relative}"
        assert (collected_static / url.removeprefix("/static/")).exists()

    # The newer breadcrumb markup must have a matching stylesheet selector.
    assert "ol.breadcrumbs" in (collected_static / "admin/css/base.css").read_text()


def test_admin_template_references_existing_versioned_stylesheets(collected_static):
    html = render_to_string(
        "admin/login.html", {"title": "Log in"}, request=RequestFactory().get("/")
    )
    assets = re.findall(r'(?:href|src)="(/static/[^\"]+)"', html)
    assert assets
    for url in assets:
        assert re.search(r"\.[a-f0-9]{12}\.", url), url
        assert (collected_static / url.removeprefix("/static/")).is_file(), url


def test_docker_keeps_build_time_assets_outside_host_bind_mounts():
    root = Path(__file__).resolve().parent.parent
    # Build-only environment assignments may precede Python; static collection
    # must still happen in the image without copying runtime credentials.
    dockerfile = (root / "Dockerfile").read_text()
    assert re.search(r"^RUN (?:[^\n]+ )?python manage\.py collectstatic --noinput$", dockerfile, re.M)
    ignored = (root / ".dockerignore").read_text().splitlines()
    assert ".env" in ignored and ".env.*" in ignored
    compose = (root / "docker-compose.yml").read_text()
    assert ":/app/static" not in compose
    assert "./media:/app/media" in compose
