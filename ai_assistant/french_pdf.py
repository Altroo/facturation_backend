"""Identify French and language-neutral PDF text locally before looking at the queue."""

from functools import lru_cache

from lingua import Language, LanguageDetectorBuilder

from .offline_translation import UNITS as NEUTRAL_UNITS, protected_segments


def _unprotected(text, terms):
    return "".join(
        " " if protected else value
        for protected, value in protected_segments(text, terms)
    ).strip()


@lru_cache(maxsize=1)
def _detector():
    return LanguageDetectorBuilder.from_languages(
        Language.FRENCH,
        Language.ENGLISH,
        Language.DUTCH,
        Language.GERMAN,
        Language.SPANISH,
        Language.ITALIAN,
        Language.PORTUGUESE,
        Language.ARABIC,
    ).build()


@lru_cache(maxsize=4096)
def _clearly_foreign(prose):
    if not any(char.isalpha() for char in prose):
        return False
    scores = _detector().compute_language_confidence_values(prose)
    best, second = scores[:2]
    french = next(score.value for score in scores if score.language == Language.FRENCH)
    # Short catalogue names, numbers, and labels such as "Location STORE N°"
    # can score in several languages. Keep them in a French document unless
    # there is clear evidence that they need translation.
    return (
        best.language != Language.FRENCH
        and best.value >= 0.45
        and best.value - second.value >= 0.15
        and best.value - french >= 0.30
    )


def split_french_sources(specs):
    originals = {}
    foreign = []
    for spec in specs:
        if any(
            _clearly_foreign(_unprotected(line, spec.protected_terms))
            for line in spec.text.splitlines()
            if line.strip().casefold() not in NEUTRAL_UNITS
        ):
            foreign.append(spec)
        else:
            originals[spec.text] = spec.text
    return originals, foreign
