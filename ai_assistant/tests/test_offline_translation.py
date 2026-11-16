import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from ai_assistant.exceptions import InvalidModelResponse, PdfTranslationEngineUnavailable
from ai_assistant.model_packages import prepare_models
from ai_assistant.offline_translation import (
    OfflineTranslationClient, detect_source_language, free_text_chunks,
    load_model, protected_segments,
)


@pytest.fixture
def client(settings, tmp_path):
    settings.PDF_TRANSLATION_MODELS_DIR = str(tmp_path)
    settings.PDF_TRANSLATION_THREADS = 2
    return OfflineTranslationClient()


def test_protected_values_never_enter_translation(client):
    text = "Montant de 1 676,80 EUR pour Marazzi ABC-123.\nLivrer avant midi."
    captured = []
    def translate(values, source, target):
        captured.extend(values)
        return ["English prose" for _ in values]
    with patch("ai_assistant.offline_translation.detect_source_language", return_value="fr"), patch.object(client, "_translate_fragments", side_effect=translate), patch("socket.create_connection", side_effect=AssertionError("No network")):
        result = client.translate_many([text], target_language="en", protected_terms=["Marazzi", "ABC-123"])[text]
    for protected in ("1 676,80", "EUR", "Marazzi", "ABC-123"):
        assert protected in result
        assert all(protected not in fragment for fragment in captured)
    assert "\n" in result


@pytest.mark.parametrize("text", ["m²", "MAD 1 234,50", "ABC-123", "123", "https://example.test/a", "qa@example.test"])
def test_codes_amounts_units_and_urls_do_not_require_models(client, text):
    with patch.object(client, "_translate_fragments") as translate:
        assert client.translate_many([text], target_language="nl")[text] == text
    translate.assert_not_called()


def test_already_translated_text_is_reused(client):
    text = "Houten stoel met een natuurlijke afwerking."
    with patch.object(client, "_translate_fragments") as translate:
        assert client.translate_many([text], target_language="nl")[text] == text
    translate.assert_not_called()


@pytest.mark.parametrize("text,language", [
    ("Chaise en bois avec une finition naturelle.", "fr"),
    ("Wooden chair with a natural finish.", "en"),
    ("Houten stoel met een natuurlijke afwerking.", "nl"),
])
def test_offline_language_detection(text, language):
    assert detect_source_language(text) == language


def test_translator_cannot_invent_numbers(client):
    with patch("ai_assistant.offline_translation.detect_source_language", return_value="fr"), patch.object(client, "_translate_fragments", return_value=["Chair 999"]):
        with pytest.raises(InvalidModelResponse):
            client.translate_many(["Chaise en bois"], target_language="en")


def test_whitespace_and_long_text_are_not_lost():
    text = " \t" + "Long texte à traduire. " * 100 + "\r\nDeuxième ligne.\n  "
    chunks = free_text_chunks(text)
    assert "".join(value for _, value in chunks) == text
    assert all(len(value) <= 400 for literal, value in chunks if not literal)
    assert "".join(value for _, value in protected_segments(text)) == text


def test_unbroken_identifier_is_retained():
    value = "A" * 1000
    assert free_text_chunks(value) == [(True, value)]


def test_tab_separated_prose_is_translated_in_bounded_chunks():
    text = "texte\t" * 120
    chunks = free_text_chunks(text)
    assert "".join(value for _, value in chunks) == text
    assert all(value.isspace() for literal, value in chunks if literal)
    assert all(len(value) <= 400 for literal, value in chunks if not literal)


def test_missing_models_fail_without_network(client):
    with patch("socket.create_connection", side_effect=AssertionError("No network")):
        with pytest.raises(PdfTranslationEngineUnavailable):
            load_model(client.root, "fr", "en", 2)


def test_french_dutch_translation_routes_through_english(client):
    from types import SimpleNamespace
    class Tokenizer:
        def encode(self, text, **kwargs): return [text]
        def decode_pieces(self, values): return " ".join(values)
    class Translator:
        def __init__(self, value): self.value = value
        def translate_batch(self, values, **kwargs):
            return [SimpleNamespace(hypotheses=[[self.value]]) for _ in values]
    calls = []
    def models(root, source, target, threads):
        calls.append((source, target))
        return Translator("English" if target == "en" else "Nederlands"), Tokenizer(), ""
    with patch("ai_assistant.offline_translation.load_model", side_effect=models):
        assert client._translate_fragments(["Français"], "fr", "nl") == ["Nederlands"]
    assert calls == [("fr", "en"), ("en", "nl")]


def test_sentencepiece_space_markers_are_removed_without_changing_underscores(client):
    from types import SimpleNamespace
    class Tokenizer:
        def encode(self, text, **kwargs): return [text]
        def decode_pieces(self, values): return "▁Wooden▁chair ref_code"
    translator = SimpleNamespace(translate_batch=lambda *args, **kwargs: [SimpleNamespace(hypotheses=[["tokens"]])])
    with patch("ai_assistant.offline_translation.load_model", return_value=(translator, Tokenizer(), "")):
        assert client._translate_fragments(["Chaise en bois"], "fr", "en") == ["Wooden chair ref_code"]


def make_package(tmp_path, *, unsafe=False):
    archives = tmp_path / "archives"
    archives.mkdir()
    archive = archives / "fr_en.argosmodel"
    with ZipFile(archive, "w") as package:
        package.writestr("translate-fr_en/metadata.json", json.dumps({"from_code":"fr","to_code":"en","package_version":"1.9"}))
        package.writestr("translate-fr_en/model/model.bin", b"model")
        package.writestr("translate-fr_en/sentencepiece.model", b"tokenizer")
        package.writestr("translate-fr_en/README.md", "Model attribution")
        if unsafe:
            package.writestr("../outside.txt", "invalid")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"pair":"fr_en","version":"1.9","url":"https://example.test/model","sha256":hashlib.sha256(archive.read_bytes()).hexdigest()}]))
    return archives, manifest


def test_model_installation_is_verified_and_idempotent(tmp_path):
    archives, manifest = make_package(tmp_path)
    directory = tmp_path / "models"
    with patch("subprocess.run", side_effect=AssertionError("No download")):
        assert prepare_models(directory, archives=archives, manifest_path=manifest)[0]["status"] == "installed"
        assert prepare_models(directory, check=True, manifest_path=manifest)[0]["status"] == "ready"
        assert prepare_models(directory, archives=archives, manifest_path=manifest)[0]["status"] == "ready"
    assert (directory / "fr_en/README.md").read_text() == "Model attribution"


def test_corrupt_model_archive_is_rejected(tmp_path):
    archives, manifest = make_package(tmp_path)
    (archives / "fr_en.argosmodel").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="checksum"):
        prepare_models(tmp_path / "models", archives=archives, manifest_path=manifest)


def test_unsafe_archive_cannot_escape_model_directory(tmp_path):
    archives, manifest = make_package(tmp_path, unsafe=True)
    with pytest.raises(ValueError, match="Unsafe path"):
        prepare_models(tmp_path / "models", archives=archives, manifest_path=manifest)
    assert not (tmp_path / "outside.txt").exists()


def test_manifest_contains_all_supported_directions():
    manifest = Path(__file__).parents[1] / "translation_models.json"
    pairs = {package["pair"] for package in json.loads(manifest.read_text())}
    assert pairs == {"fr_en", "en_fr", "en_nl", "nl_en"}


def test_setup_command_checks_models_without_network(tmp_path):
    from django.core.management import call_command, CommandError
    from io import StringIO
    with patch("subprocess.run", side_effect=AssertionError("No download")):
        with pytest.raises(CommandError, match="Missing or incomplete"):
            call_command("prepare_pdf_translation_models", directory=str(tmp_path), check=True, stdout=StringIO())
