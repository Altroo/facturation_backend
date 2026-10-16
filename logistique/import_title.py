"""Read import-title documents locally, without storing them or changing a dossier.

Extraction is deliberately conservative: only labelled, unambiguous values are
suggested. The caller must show them for confirmation before saving them.
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
import time
import unicodedata
import warnings
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PAGES = 5
MAX_TEXT_SIZE = 256 * 1024
MAX_IMAGE_PIXELS = 25_000_000
EXTRACTION_TIMEOUT = 60

_FIELD_NAMES = {
    "numero_domiciliation": "numéro de domiciliation",
    "banque": "banque",
    "montant_titre_importation": "montant du titre d'importation",
    "devise_titre_importation": "devise du titre d'importation",
    "date_titre_importation": "date du titre d'importation",
}
_LABELS = {
    "numero_domiciliation": (
        r"(?:n(?:umero|[°ºo])?\.?\s*(?:de\s+)?domiciliation|"
        r"domiciliation\s+(?:number|no\.?|n[°º])|domiciliation)"
    ),
    "banque": (
        r"(?:banque\s+(?:domiciliataire|de\s+domiciliation)|"
        r"domiciliat(?:ing|ion)\s+bank|bank\s+name|banque|bank)"
    ),
    "montant_titre_importation": (
        r"(?:montant\s+(?:total\s+)?(?:du\s+)?titre(?:\s+d['’]importation)?|"
        r"montant\s+total|total\s+amount|import\s+title\s+amount|montant|amount)"
    ),
    "devise_titre_importation": (
        r"(?:devise\s+(?:du\s+)?titre(?:\s+d['’]importation)?|"
        r"devise\s+(?:de\s+)?(?:reglement|facturation)|"
        r"import\s+title\s+currency|devise|currency)"
    ),
    "date_titre_importation": (
        r"(?:date\s+(?:du\s+)?titre(?:\s+d['’]importation)?|date\s+ti|"
        r"date\s+de\s+domiciliation|date\s+d['’]emission|date\s+of\s+issue|"
        r"issue\s+date|import\s+title\s+date)"
    ),
}
_LABEL_PATTERN = "|".join(_LABELS.values())
_LABEL_MATCHERS = {
    key: re.compile(r"^" + expression + r"(?=\s|[:=]|$)")
    for key, expression in _LABELS.items()
}
_COLUMN_BOUNDARY = re.compile(
    r"(?:\s{2,}|\s*[|;]\s*)(?=(?:" + _LABEL_PATTERN + r")(?=\s|[:=]|$))"
)
_CURRENCIES = {
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "€": "EUR",
    "usd": "USD",
    "us$": "USD",
    "mad": "MAD",
    "dirham": "MAD",
    "dirhams": "MAD",
}
_CURRENCY_RE = re.compile(r"(?<!\w)(?:eur|euros?|usd|us\$|mad|dirhams?)(?!\w)|€")
_MONTHS = {
    "janvier": 1,
    "january": 1,
    "jan": 1,
    "fevrier": 2,
    "february": 2,
    "feb": 2,
    "mars": 3,
    "march": 3,
    "mar": 3,
    "avril": 4,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "juin": 6,
    "june": 6,
    "jun": 6,
    "juillet": 7,
    "july": 7,
    "jul": 7,
    "aout": 8,
    "august": 8,
    "aug": 8,
    "septembre": 9,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "octobre": 10,
    "october": 10,
    "oct": 10,
    "novembre": 11,
    "november": 11,
    "nov": 11,
    "decembre": 12,
    "december": 12,
    "dec": 12,
}


class _ExtractionError(Exception):
    """An unsafe, unreadable or unavailable local extraction step."""


def _fold(value):
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    ).lower()


def _currency_values(value):
    return {_CURRENCIES[match.group()] for match in _CURRENCY_RE.finditer(_fold(value))}


def _parse_amount(value):
    value = _CURRENCY_RE.sub("", _fold(value)).strip()
    # Spaces may group thousands; signs, percentages and unrelated words are unsafe.
    if not re.fullmatch(r"[0-9][0-9 ,.\u00a0\u202f]*", value):
        return None
    value = value.replace("\u00a0", " ").replace("\u202f", " ").strip()
    if " " in value:
        if not re.fullmatch(r"\d{1,3}(?: \d{3})+(?:[.,]\d{1,2})?", value):
            return None
        value = value.replace(" ", "")
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        pattern = (
            r"\d{1,3}(?:"
            + re.escape(grouping_separator)
            + r"\d{3})+"
            + re.escape(decimal_separator)
            + r"\d{1,2}"
        )
        if not re.fullmatch(pattern, value):
            return None
        value = value.replace(grouping_separator, "").replace(decimal_separator, ".")
    elif "," in value or "." in value:
        # A single separator followed by three digits can be decimal or thousands.
        if re.fullmatch(r"\d{1,3}(?:,\d{3}){2,}|\d{1,3}(?:\.\d{3}){2,}", value):
            value = value.replace(",", "").replace(".", "")
        elif re.fullmatch(r"\d+[.,]\d{1,2}", value):
            value = value.replace(",", ".")
        else:
            return None
    try:
        amount = Decimal(value)
        if not Decimal("0") < amount <= Decimal("9999999999.99"):
            return None
        return format(amount.quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        return None


def _parse_date(value):
    value = _fold(value).strip().rstrip(".")
    parts = None
    match = re.fullmatch(r"(\d{4})[-/](\d{2})[-/](\d{2})", value)
    if match:
        parts = tuple(map(int, match.groups()))
    match = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", value)
    if match:
        first, second, year = map(int, match.groups())
        if first == second or first > 12:
            parts = (year, second, first)
        elif second > 12:
            parts = (year, first, second)
        else:
            return None
    match = re.fullmatch(r"(\d{1,2})\s+([a-z]+)\.?\s+(\d{4})", value)
    if match and match[2] in _MONTHS:
        parts = (int(match[3]), _MONTHS[match[2]], int(match[1]))
    match = re.fullmatch(r"([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", value)
    if match and match[1] in _MONTHS:
        parts = (int(match[3]), _MONTHS[match[1]], int(match[2]))
    try:
        return date(*parts).isoformat() if parts else None
    except ValueError:
        return None


def _labelled_values(text):
    # Preserve value spelling while matching French accents and English labels.
    lines = []
    for line in text.splitlines():
        if "\x00" in line:
            continue
        original = line.strip()
        folded = _fold(original)
        starts = [0] + [match.end() for match in _COLUMN_BOUNDARY.finditer(folded)]
        ends = [match.start() for match in _COLUMN_BOUNDARY.finditer(folded)] + [
            len(original)
        ]
        lines.extend(original[start:end].strip() for start, end in zip(starts, ends))
    for index, line in enumerate(lines):
        folded = _fold(line)
        for key, pattern in _LABEL_MATCHERS.items():
            match = pattern.match(folded)
            if not match:
                continue
            tail = line[match.end() :]
            if not tail.strip(" :=\t"):
                value = lines[index + 1] if index + 1 < len(lines) else ""
                if any(p.match(_fold(value)) for p in _LABEL_MATCHERS.values()):
                    value = ""
            elif tail.startswith((":", "=")) or re.match(r"\s*[:=]", tail):
                value = tail.lstrip(" :=\t")
            elif re.match(r"\s{2,}\S", tail):
                value = tail.strip()
            else:
                # Avoid reading 'Bank address' or 'Montant TVA' as the field value.
                value = ""
            if value:
                yield key, value.strip()
            break


def parse_import_title_text(text):
    """Return JSON-safe suggestions from explicit French/English document labels."""
    candidates = {key: set() for key in _FIELD_NAMES}
    invalid = set()
    for key, value in _labelled_values(text):
        parsed = None
        if key == "montant_titre_importation":
            parsed = _parse_amount(value)
            currencies = _currency_values(value)
            candidates["devise_titre_importation"].update(currencies)
        elif key == "devise_titre_importation":
            currencies = _currency_values(value)
            candidates[key].update(currencies)
            if len(currencies) != 1:
                invalid.add(key)
            continue
        elif key == "date_titre_importation":
            parsed = _parse_date(value)
        elif key == "numero_domiciliation":
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /._-]{0,99}", value) and re.search(
                r"\d", value
            ):
                parsed = value
        elif key == "banque" and 2 <= len(value) <= 255:
            parsed = value
        if parsed is None:
            invalid.add(key)
        else:
            candidates[key].add(parsed)
    fields = {
        key: next(iter(values))
        for key, values in candidates.items()
        if len(values) == 1 and key not in invalid
    }
    missing = [_FIELD_NAMES[key] for key in _FIELD_NAMES if key not in fields]
    messages = []
    if missing:
        messages.append(
            "Lecture incertaine ou information absente : "
            + ", ".join(missing)
            + ". Veuillez renseigner ou vérifier ces champs manuellement."
        )
    return {"fields": fields, "warnings": messages}


def _run(arguments, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _ExtractionError("Le délai de lecture du document est dépassé.")
    try:
        return subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            timeout=min(20, remaining),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ExtractionError(
            "La lecture automatique de ce document est indisponible."
        ) from exc


def _read_text(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_TEXT_SIZE + 1)
    if len(data) > MAX_TEXT_SIZE:
        raise _ExtractionError(
            "Le contenu du document est trop volumineux pour être lu."
        )
    return data.decode("utf-8", errors="replace")


def _ocr(paths, directory, deadline):
    texts = []
    for index, image in enumerate(paths):
        output = directory / f"ocr-{index}"
        _run(
            ["tesseract", str(image), str(output), "-l", "fra+eng", "--psm", "6"],
            deadline,
        )
        texts.append(_read_text(output.with_suffix(".txt")))
    text = "\n".join(texts)
    if len(text.encode("utf-8")) > MAX_TEXT_SIZE:
        raise _ExtractionError(
            "Le contenu du document est trop volumineux pour être lu."
        )
    return text


def _pdf_text(data, directory, deadline):
    source = directory / "document.pdf"
    source.write_bytes(data)
    info = _run(["pdfinfo", str(source)], deadline).stdout.decode(
        "utf-8", errors="replace"
    )
    pages = re.search(r"^Pages:\s*(\d+)\s*$", info, flags=re.MULTILINE)
    if not pages or not 1 <= int(pages[1]) <= MAX_PAGES:
        raise _ExtractionError("Le document doit contenir entre 1 et 5 pages.")
    output = directory / "document.txt"
    try:
        _run(
            [
                "pdftotext",
                "-layout",
                "-f",
                "1",
                "-l",
                pages[1],
                str(source),
                str(output),
            ],
            deadline,
        )
        text = _read_text(output)
    except _ExtractionError:
        text = ""
    if text.strip() and parse_import_title_text(text)["fields"]:
        return text
    _run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            pages[1],
            "-r",
            "150",
            "-scale-to",
            "2000",
            "-png",
            str(source),
            str(directory / "page"),
        ],
        deadline,
    )
    images = sorted(directory.glob("page-*.png"))
    if len(images) != int(pages[1]):
        raise _ExtractionError("Les pages du document n'ont pas pu être lues.")
    return _ocr(images, directory, deadline)


def _image_text(data, suffix, directory, deadline):
    from PIL import Image

    try:
        return _decode_image(data, suffix, directory, deadline, Image)
    except Image.DecompressionBombError as exc:
        raise _ExtractionError(
            "L'image est trop grande pour être lue automatiquement."
        ) from exc


def _decode_image(data, suffix, directory, deadline, Image):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            expected = "PNG" if suffix == ".png" else "JPEG"
            if image.format != expected or getattr(image, "n_frames", 1) != 1:
                raise _ExtractionError(
                    "Le contenu du fichier ne correspond pas à son format."
                )
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise _ExtractionError(
                    "L'image est trop grande pour être lue automatiquement."
                )
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.thumbnail((2000, 2000))
            target = directory / "image.png"
            image.convert("RGB").save(target, format="PNG")
    return _ocr([target], directory, deadline)


def extract_import_title(file):
    """Suggest import-title values; never save anything or invoke a remote service.

    Uploads are limited to 10 MB, PDFs to five pages, and local commands to a
    shared deadline. The upload is rewound even if extraction fails.
    """
    try:
        suffix = Path(str(getattr(file, "name", ""))).suffix.lower()
        if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
            raise _ExtractionError(
                "La lecture automatique accepte les fichiers PDF, PNG et JPEG."
            )
        if getattr(file, "size", 0) > MAX_FILE_SIZE:
            raise _ExtractionError("Le fichier ne doit pas dépasser 10 Mo.")
        file.seek(0)
        data = file.read(MAX_FILE_SIZE + 1)
        if not isinstance(data, bytes) or not data:
            raise _ExtractionError("Le fichier est vide ou illisible.")
        if len(data) > MAX_FILE_SIZE:
            raise _ExtractionError("Le fichier ne doit pas dépasser 10 Mo.")
        if suffix == ".pdf" and not data.startswith(b"%PDF-"):
            raise _ExtractionError("Le contenu du fichier n'est pas un PDF valide.")
        deadline = time.monotonic() + EXTRACTION_TIMEOUT
        with tempfile.TemporaryDirectory(prefix="logistics-import-title-") as temporary:
            directory = Path(temporary)
            text = (
                _pdf_text(data, directory, deadline)
                if suffix == ".pdf"
                else _image_text(data, suffix, directory, deadline)
            )
        return parse_import_title_text(text)
    except _ExtractionError as exc:
        message = str(exc)
    except (OSError, ValueError, ImportError, SyntaxError, Warning):
        message = "Le document n'a pas pu être lu automatiquement."
    finally:
        try:
            file.seek(0)
        except (OSError, ValueError, AttributeError):
            pass
    return {
        "fields": {},
        "warnings": [message + " Veuillez renseigner les champs manuellement."],
    }
