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
    load_model, numeric_token_sequences, protected_segments,
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


@pytest.mark.parametrize("name", ["ExampleCoat®", "ExampleCoat™"])
def test_registered_names_never_enter_inference(client, name):
    text = f"Revêtement {name} pour une finition naturelle."
    captured = []
    def translate(values, source, target):
        captured.extend(values)
        return ["Translated prose" for _ in values]
    with patch("ai_assistant.offline_translation.detect_source_language", return_value="fr"), patch.object(client, "_translate_fragments", side_effect=translate):
        result = client.translate_many([text], target_language="en")[text]
    assert name in result
    assert all(name not in fragment for fragment in captured)


@pytest.mark.parametrize("reference", ["Ø200", "ø350", "Φ300", "ÉTÉ123", "C₂", "R²", "ABC-123", "A_123/B-45"])
def test_unicode_measurements_and_references_never_enter_inference(client, reference):
    text = f"Article {reference} en acier poli."
    captured = []
    def translate(values, source, target):
        captured.extend(values)
        return ["Translated prose" for _ in values]
    with patch("ai_assistant.offline_translation.detect_source_language", return_value="fr"), patch.object(client, "_translate_fragments", side_effect=translate):
        result = client.translate_many([text], target_language="nl")[text]
    assert reference in result
    assert all(reference not in fragment for fragment in captured)
    assert all(not any(character.isnumeric() for character in fragment) for fragment in captured)


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


@pytest.mark.parametrize("unit", ["m²", "m³", "cm²", "mm³", "m2", "m3"])
@pytest.mark.parametrize("separator", [" ", ""])
def test_dimensions_never_enter_inference(client, unit, separator):
    text = f"Surface totale : 150{separator}{unit}. Finition blanche."
    captured = []
    def translate(values, source, target):
        captured.extend(values)
        return ["Translated prose" for _ in values]
    with patch("ai_assistant.offline_translation.detect_source_language", return_value="fr"), patch.object(client, "_translate_fragments", side_effect=translate):
        result = client.translate_many([text], target_language="nl")[text]
    assert f"150{separator}{unit}" in result
    assert all(unit not in fragment for fragment in captured)
    assert [v for literal, v in protected_segments(result) if literal] == [v for literal, v in protected_segments(text) if literal]


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


@pytest.mark.parametrize("text", [
    "Compatible avec 12345. Corps en acier.",
    "Longueur 100mm, finition blanche.",
    "Articles 12345, 67890. Corps blanc.",
    "Référence ABC-123; fixation murale.",
])
def test_separators_after_protected_values_do_not_enter_inference(client, text):
    captured = []
    def translate(values, source, target):
        captured.extend(values)
        return ["Translated prose" for _ in values]
    with patch("ai_assistant.offline_translation.detect_source_language", return_value="fr"), patch.object(client, "_translate_fragments", side_effect=translate):
        result = client.translate_many([text], target_language="en")[text]
    assert [v for literal, v in protected_segments(result) if literal] == [v for literal, v in protected_segments(text) if literal]
    assert all(value[0].isalnum() and value[-1].isalnum() for value in captured)
    assert "." in result


@pytest.mark.parametrize("text", [". Corps blanc. ", " ; finition blanche!", "...", "\t, \n", "_nom_", "'texte'"])
def test_edge_punctuation_is_preserved_exactly(text):
    chunks = free_text_chunks(text)
    assert "".join(value for _, value in chunks) == text
    assert all(value[0].isalnum() and value[-1].isalnum() for literal, value in chunks if not literal)


def test_missing_models_fail_without_network(client):
    with patch("socket.create_connection", side_effect=AssertionError("No network")):
        with pytest.raises(PdfTranslationEngineUnavailable):
            load_model(client.root, "fr", "en", 2)


def test_french_dutch_translation_routes_through_english(client):
    from types import SimpleNamespace
    class Tokenizer:
        def get_piece_size(self): return 1
        def id_to_piece(self, index): return "word"
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
        def get_piece_size(self): return 1
        def id_to_piece(self, index): return "word"
        def encode(self, text, **kwargs): return [text]
        def decode_pieces(self, values): return "▁Wooden▁chair ref_code"
    translator = SimpleNamespace(translate_batch=lambda *args, **kwargs: [SimpleNamespace(hypotheses=[["tokens"]])])
    with patch("ai_assistant.offline_translation.load_model", return_value=(translator, Tokenizer(), "")):
        assert client._translate_fragments(["Chaise en bois"], "fr", "en") == ["Wooden chair ref_code"]


def test_numeric_surface_forms_are_suppressed_during_prose_decoding(client):
    from types import SimpleNamespace
    pieces = ["<unk>", "four", "▁4", "2", "m²", "chair"]
    class Tokenizer:
        def get_piece_size(self): return len(pieces)
        def id_to_piece(self, index): return pieces[index]
        def encode(self, text, **kwargs): return [text]
        def decode_pieces(self, values): return "four-way finish"
    calls = []
    def translate(values, **options):
        calls.append(options)
        return [SimpleNamespace(hypotheses=[["four", "way", "finish"]])]
    tokenizer = Tokenizer()
    translator = SimpleNamespace(translate_batch=translate)
    with patch("ai_assistant.offline_translation.load_model", return_value=(translator, tokenizer, "")):
        assert client._translate_fragments(["finition quatre voies"], "fr", "en") == ["four-way finish"]
    assert calls[0]["suppress_sequences"] == [["▁4"], ["2"], ["m²"]]
    assert calls[0]["no_repeat_ngram_size"] == 3
    assert numeric_token_sequences(tokenizer) == calls[0]["suppress_sequences"]


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
