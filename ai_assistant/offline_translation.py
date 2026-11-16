"""Offline PDF prose translation. Names, references and numbers never enter inference."""

import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .exceptions import InvalidModelResponse, PdfTranslationEngineUnavailable

LANGUAGES = ("fr", "en", "nl")
PROTECTED_PATTERNS = (
    r"https?://[^\s<>]+",
    r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
    r"\b[\w-]+[®™]",
    r"\b(?:MAD|DHS?|EUR|USD)\b|[$€£]",
    r"(?<![^\W\d])(?:mm|cm|m)[²³23](?!\w)",
    r"\b(?=[\w/-]*[^\W\d_])(?=[\w/-]*[\d⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉])\w+(?:[-/]\w+)*\b",
    r"(?<!\w)[-+]?\d+(?:[\s.,:/×x-]\d+)*(?:\s*%)?",
)
UNITS = frozenset(("m", "m²", "m³", "m2", "m3", "ml", "kg", "g", "l", "cm", "mm", "u"))


def protected_segments(text, protected_terms=()):
    spans = []
    for pattern in PROTECTED_PATTERNS:
        spans.extend((m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE))
    for term in protected_terms:
        if isinstance(term, str) and term.strip():
            spans.extend(
                (m.start(), m.end())
                for m in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)
            )
    merged = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    result, cursor = [], 0
    for start, end in merged:
        if start > cursor:
            result.append((False, text[cursor:start]))
        result.append((True, text[start:end]))
        cursor = end
    if cursor < len(text):
        result.append((False, text[cursor:]))
    return result

@lru_cache(maxsize=1)
def language_detector():
    from lingua import Language, LanguageDetectorBuilder

    return LanguageDetectorBuilder.from_languages(
        Language.FRENCH, Language.ENGLISH, Language.DUTCH
    ).build()


def detect_source_language(text):
    from lingua import Language

    detected = language_detector().detect_language_of(text)
    return {Language.FRENCH: "fr", Language.ENGLISH: "en", Language.DUTCH: "nl"}.get(detected, "fr")

@lru_cache(maxsize=4)
def load_model(root, source_language, target_language, threads):
    import ctranslate2
    import sentencepiece

    directory = Path(root) / f"{source_language}_{target_language}"
    try:
        metadata = json.loads((directory / "metadata.json").read_text())
        if (metadata["from_code"], metadata["to_code"]) != (source_language, target_language):
            raise ValueError("Incorrect translation model direction")
        tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(directory / "sentencepiece.model"))
        translator = ctranslate2.Translator(
            str(directory / "model"), device="cpu", compute_type="int8",
            inter_threads=1, intra_threads=threads,
        )
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        raise PdfTranslationEngineUnavailable() from exc
    return translator, tokenizer, metadata.get("target_prefix", "")


@lru_cache(maxsize=4)
def numeric_token_sequences(tokenizer):
    # Free prose excludes source amounts and references. Decode word-based
    # numbers as words too, so "four-way" cannot introduce an unchecked "4".
    tokens = (tokenizer.id_to_piece(index) for index in range(tokenizer.get_piece_size()))
    return [[token] for token in tokens if any(character.isnumeric() for character in token)]


def free_text_chunks(text, limit=400):
    """Keep exact whitespace and line breaks while bounding inference inputs."""
    chunks = []
    for part in re.split(r"(\r\n|\n|\r)", text):
        if not part:
            continue
        if not any(character.isalnum() for character in part):
            chunks.append((True, part))
            continue
        # Models may drop leading punctuation. Keep separators outside inference
        # so a code followed by ". Description" cannot become "123Description".
        leading = re.match(r"^[\W_]*", part).group()
        trailing = re.search(r"[\W_]*$", part).group()
        remaining = part[len(leading):len(part) - len(trailing) if trailing else None]
        if leading:
            chunks.append((True, leading))
        while len(remaining) > limit:
            boundaries = list(re.finditer(r"\s+", remaining[:limit + 1]))
            boundary = boundaries[-1].start() if boundaries else -1
            if boundary < 1:
                # An unbroken identifier is data, rather than translatable prose.
                match = re.search(r"\s", remaining)
                boundary = match.start() if match else len(remaining)
                chunks.append((True, remaining[:boundary]))
            else:
                chunks.append((False, remaining[:boundary]))
            remaining = remaining[boundary:]
            separator = remaining[:len(remaining) - len(remaining.lstrip())]
            if separator:
                chunks.append((True, separator))
            remaining = remaining.lstrip()
        if remaining:
            chunks.append((False, remaining))
        if trailing:
            chunks.append((True, trailing))
    return chunks


class OfflineTranslationClient:
    def __init__(self):
        self.root = str(settings.PDF_TRANSLATION_MODELS_DIR)
        self.threads = settings.PDF_TRANSLATION_THREADS

    def _translate_fragments(self, fragments, source_language, target_language):
        if not fragments or source_language == target_language:
            return fragments
        if "en" not in (source_language, target_language):
            english = self._translate_fragments(fragments, source_language, "en")
            return self._translate_fragments(english, "en", target_language)
        translator, tokenizer, prefix = load_model(
            self.root, source_language, target_language, self.threads
        )
        encoded = [tokenizer.encode(text, out_type=str) for text in fragments]
        results = translator.translate_batch(
            encoded, target_prefix=[[prefix]] * len(encoded) if prefix else None,
            beam_size=2, max_batch_size=16, replace_unknowns=True, no_repeat_ngram_size=3,
            max_input_length=0, max_decoding_length=1024,
            suppress_sequences=numeric_token_sequences(tokenizer),
        )
        if len(results) != len(fragments):
            raise InvalidModelResponse()
        translated = []
        for result in results:
            tokens = result.hypotheses[0]
            if len(tokens) >= 1024:
                raise InvalidModelResponse()
            # Argos packages can copy unknown surface tokens containing the SPM
            # space marker. Keep literal underscores while removing that marker.
            value = tokenizer.decode_pieces(tokens).replace("▁", " ")
            if prefix and value.startswith(prefix):
                value = value[len(prefix):]
            if not value.strip():
                raise InvalidModelResponse()
            translated.append(value.strip())
        return translated

    def translate_many(self, texts, *, target_language, protected_terms=(), context="document"):
        if target_language not in LANGUAGES:
            raise ValueError("Unsupported PDF language")
        result = {}
        for text in dict.fromkeys(value for value in texts if isinstance(value, str) and value.strip()):
            segments = protected_segments(text, protected_terms)
            prose = " ".join(value for literal, value in segments if not literal)
            if not any(letter.isalpha() for letter in prose) or text.strip().casefold() in UNITS:
                result[text] = text
                continue
            source_language = detect_source_language(prose)
            if source_language == target_language:
                result[text] = text
                continue
            parts = []
            for literal, value in segments:
                parts.extend([(True, value)] if literal else free_text_chunks(value))
            fragments = [value for literal, value in parts if not literal and any(c.isalpha() for c in value)]
            translated = iter(self._translate_fragments(fragments, source_language, target_language))
            value = "".join(
                next(translated) if not literal and any(c.isalpha() for c in value) else value
                for literal, value in parts
            )
            original_values = [part for literal, part in segments if literal]
            output_values = [part for literal, part in protected_segments(value, protected_terms) if literal]
            if original_values != output_values:
                raise InvalidModelResponse()
            result[text] = value
        return result
