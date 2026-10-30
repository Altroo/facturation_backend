"""Conservative parsing and failure behaviour of local import-title extraction."""

import io
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from logistique.import_title import (
    MAX_FILE_SIZE,
    _parse_amount,
    _parse_date,
    extract_import_title,
    parse_import_title_text,
)

FRENCH_TITLE = """
TITRE D'IMPORTATION
N° de domiciliation : TI-2026/12345
Banque domiciliataire : Banque Populaire
Montant total : 12 345,67 EUR
Devise : EUR
Date du titre d'importation : 2026-10-07
"""
ENGLISH_TITLE = """
Import title
Domiciliation number: IMP-7788
Bank name: Example Bank
Total amount: USD 12,345.67
Currency: USD
Issue date: October 7, 2026
"""


def upload(content=b"%PDF-1.7\nmock", name="titre.pdf"):
    file = io.BytesIO(content)
    file.name = name
    return file


class ImportTitleParsingTests(unittest.TestCase):
    def test_french_title_fields_are_json_safe(self):
        result = parse_import_title_text(FRENCH_TITLE)
        self.assertEqual(
            result,
            {
                "fields": {
                    "numero_domiciliation": "TI-2026/12345",
                    "banque": "Banque Populaire",
                    "montant_titre_importation": "12345.67",
                    "devise_titre_importation": "EUR",
                    "date_titre_importation": "2026-10-07",
                },
                "warnings": [],
            },
        )

    def test_english_title(self):
        result = parse_import_title_text(ENGLISH_TITLE)
        self.assertEqual(len(result["fields"]), 5)
        self.assertEqual(result["fields"]["date_titre_importation"], "2026-10-07")
        self.assertEqual(result["fields"]["devise_titre_importation"], "USD")
        self.assertEqual(result["fields"]["montant_titre_importation"], "12345.67")

    def test_label_on_next_line_and_columns(self):
        result = parse_import_title_text(
            "Banque :\nSociété Générale\nMontant total : 18 000,00  Devise : MAD"
        )["fields"]
        self.assertEqual(result["banque"], "Société Générale")
        self.assertEqual(result["montant_titre_importation"], "18000.00")
        self.assertEqual(result["devise_titre_importation"], "MAD")

    def test_amount_formats(self):
        for text, expected in [
            ("12 345,67 EUR", "12345.67"),
            ("USD 12,345.67", "12345.67"),
            ("12.345,67", "12345.67"),
            ("18000", "18000.00"),
            ("18\u202f000,50", "18000.50"),
            ("0.99", "0.99"),
            ("9999999999.99", "9999999999.99"),
            ("1,234,567", "1234567.00"),
            ("1.234.567", "1234567.00"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(_parse_amount(text), expected)

    def test_ambiguous_invalid_or_out_of_range_amounts_are_omitted(self):
        for text in [
            "18.000",
            "18,000",
            "1,23,456.00",
            "12 34,50",
            "-50",
            "0",
            "10000000000",
            "30%",
            "12.34.56",
            "100 euros et 20 dollars",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(_parse_amount(text))

    def test_safe_dates_and_ambiguous_dates(self):
        for text in [
            "07/10/2026",
            "10-07-2026",
            "31/02/2026",
            "2026-13-07",
            "26/10/07",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(_parse_date(text))
        for text, expected in [
            ("2026-10-07", "2026-10-07"),
            ("23/10/2026", "2026-10-23"),
            ("10/23/2026", "2026-10-23"),
            ("11/11/2026", "2026-11-11"),
            ("7 octobre 2026", "2026-10-07"),
            ("7 février 2026", "2026-02-07"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(_parse_date(text), expected)

    def test_conflicting_values_omitted_instead_of_picking_one(self):
        result = parse_import_title_text(
            FRENCH_TITLE + "\nMontant total : 99,00 USD\nBanque : Autre banque"
        )
        for field in [
            "banque",
            "devise_titre_importation",
            "montant_titre_importation",
        ]:
            self.assertNotIn(field, result["fields"])
        self.assertTrue(result["warnings"])

    def test_invalid_duplicate_does_not_get_silently_ignored(self):
        result = parse_import_title_text("Montant: 100,00\nMontant: illisible")
        self.assertNotIn("montant_titre_importation", result["fields"])

    def test_unlabelled_numbers_and_other_dates_not_guessed(self):
        result = parse_import_title_text(
            "Facture 123456 EUR 30000\nDate de livraison: 2026-10-07\n"
            "Montant TVA: 500,00\nBank address: 123 Main Street\nDate: 2026-10-07"
        )
        self.assertEqual(result["fields"], {})
        self.assertIn("manuellement", result["warnings"][0])

    def test_bare_dollar_symbol_does_not_fabricate_a_currency(self):
        self.assertNotIn(
            "devise_titre_importation", parse_import_title_text("Devise: $")["fields"]
        )

    def test_identical_repeated_header_values_are_allowed(self):
        self.assertEqual(
            parse_import_title_text(FRENCH_TITLE * 2),
            parse_import_title_text(FRENCH_TITLE),
        )


class ImportTitleExtractionTests(unittest.TestCase):
    @unittest.skipUnless(
        shutil.which("pdfinfo") and shutil.which("pdftotext"), "Poppler not installed"
    )
    def test_real_text_pdf_integration(self):
        from reportlab.pdfgen import canvas

        document = io.BytesIO()
        pdf = canvas.Canvas(document)
        content = pdf.beginText(50, 780)
        content.setFont("Helvetica", 12)
        for line in FRENCH_TITLE.splitlines():
            content.textLine(line)
        pdf.drawText(content)
        pdf.save()
        file = upload(document.getvalue())
        self.assertEqual(
            extract_import_title(file), parse_import_title_text(FRENCH_TITLE)
        )
        self.assertEqual(file.tell(), 0)

    def test_text_pdf_commands_use_fixed_paths_and_cleanup(self):
        seen_directories = []

        def run(args, **kwargs):
            self.assertIsInstance(args, list)
            self.assertNotIn("shell", kwargs)
            self.assertLessEqual(kwargs["timeout"], 20)
            directory = Path(args[-1]).parent
            seen_directories.append(directory)
            if args[0] == "pdfinfo":
                return subprocess.CompletedProcess(args, 0, stdout=b"Pages: 2\n")
            if args[0] == "pdftotext":
                Path(args[-1]).write_text(FRENCH_TITLE)
                return subprocess.CompletedProcess(args, 0, stdout=b"")
            self.fail("OCR must not run for a readable text PDF")

        file = upload(name="../../$(touch hacked); titre.pdf")
        file.seek(4)
        with patch("logistique.import_title.subprocess.run", side_effect=run):
            result = extract_import_title(file)
        self.assertEqual(len(result["fields"]), 5)
        self.assertEqual(file.tell(), 0)
        self.assertTrue(all(not path.exists() for path in seen_directories))

    def test_scan_uses_french_english_ocr_and_bounded_pages(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            if args[0] == "pdfinfo":
                return subprocess.CompletedProcess(args, 0, stdout=b"Pages: 1\n")
            if args[0] == "pdftotext":
                Path(args[-1]).write_text("PortNet")
            elif args[0] == "pdftoppm":
                Path(args[-1] + "-1.png").write_bytes(b"image")
            elif args[0] == "tesseract":
                Path(args[2] + ".txt").write_text(FRENCH_TITLE)
            return subprocess.CompletedProcess(args, 0, stdout=b"")

        with patch("logistique.import_title.subprocess.run", side_effect=run):
            result = extract_import_title(upload())
        self.assertEqual(len(result["fields"]), 5)
        ocr = next(args for args in calls if args[0] == "tesseract")
        self.assertEqual(ocr[3:5], ["-l", "fra+eng"])
        render = next(args for args in calls if args[0] == "pdftoppm")
        self.assertIn("2000", render)

    def test_oversize_unsupported_empty_and_fake_pdf_never_spawn_commands(self):
        large = upload()
        large.size = MAX_FILE_SIZE + 1
        actual_large = upload(b"%PDF-" + b"x" * MAX_FILE_SIZE)
        for file in [
            large,
            actual_large,
            upload(name="document.docx"),
            upload(b""),
            upload(b"not a PDF"),
        ]:
            with self.subTest(name=file.name):
                with patch("logistique.import_title.subprocess.run") as run:
                    result = extract_import_title(file)
                self.assertEqual(result["fields"], {})
                self.assertIn("manuellement", result["warnings"][0])
                self.assertEqual(file.tell(), 0)
                run.assert_not_called()

    def test_more_than_five_pages_rejected_before_rendering(self):
        with patch(
            "logistique.import_title.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout=b"Pages: 6\n"),
        ) as run:
            result = extract_import_title(upload())
        self.assertEqual(result["fields"], {})
        self.assertIn("5 pages", result["warnings"][0])
        self.assertEqual(run.call_count, 1)

    def test_unavailable_commands_timeout_and_invalid_pdf_do_not_raise(self):
        errors = [
            FileNotFoundError(),
            subprocess.TimeoutExpired("pdfinfo", 20),
            subprocess.CalledProcessError(1, "pdfinfo"),
            OSError("cannot read"),
        ]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                file = upload()
                with patch("logistique.import_title.subprocess.run", side_effect=error):
                    result = extract_import_title(file)
                self.assertEqual(result["fields"], {})
                self.assertIn("manuellement", result["warnings"][0])
                self.assertEqual(file.tell(), 0)

    def test_image_decoding_failure_falls_back_to_manual(self):
        with patch(
            "logistique.import_title._image_text", side_effect=ValueError("bad image")
        ):
            result = extract_import_title(upload(b"bad-image", name="titre.png"))
        self.assertEqual(result["fields"], {})
        self.assertIn("manuellement", result["warnings"][0])

    def test_real_png_and_jpeg_are_decoded_before_ocr(self):
        from PIL import Image

        for format_name, suffix in [("PNG", ".png"), ("JPEG", ".jpg")]:
            with self.subTest(format=format_name):
                content = io.BytesIO()
                Image.new("RGB", (80, 50), "white").save(content, format=format_name)
                file = upload(content.getvalue(), name="titre" + suffix)
                with patch(
                    "logistique.import_title._ocr", return_value=FRENCH_TITLE
                ) as ocr:
                    result = extract_import_title(file)
                self.assertEqual(len(result["fields"]), 5)
                self.assertEqual(file.tell(), 0)
                self.assertFalse(ocr.call_args.args[0][0].exists())

    def test_wrong_image_format_and_corrupt_image_never_run_ocr(self):
        from PIL import Image

        content = io.BytesIO()
        Image.new("RGB", (20, 20)).save(content, format="PNG")
        for file in [
            upload(content.getvalue(), name="titre.jpeg"),
            upload(b"broken", name="titre.png"),
        ]:
            with patch("logistique.import_title._ocr") as ocr:
                result = extract_import_title(file)
            self.assertEqual(result["fields"], {})
            self.assertIn("manuellement", result["warnings"][0])
            ocr.assert_not_called()

    def test_image_decompression_bomb_has_manual_fallback(self):
        from PIL import Image

        with patch("PIL.Image.open", side_effect=Image.DecompressionBombError()):
            result = extract_import_title(upload(b"image", name="titre.png"))
        self.assertEqual(result["fields"], {})
        self.assertIn("trop grande", result["warnings"][0])

    def test_global_deadline_prevents_new_subprocess(self):
        with patch("logistique.import_title.time.monotonic", side_effect=[0, 61]):
            with patch("logistique.import_title.subprocess.run") as run:
                result = extract_import_title(upload())
        self.assertEqual(result["fields"], {})
        run.assert_not_called()

    def test_pdftotext_failure_falls_back_to_scan(self):
        def run(args, **kwargs):
            if args[0] == "pdfinfo":
                return subprocess.CompletedProcess(args, 0, stdout=b"Pages: 1\n")
            if args[0] == "pdftotext":
                raise subprocess.CalledProcessError(1, args)
            if args[0] == "pdftoppm":
                Path(args[-1] + "-1.png").write_bytes(b"image")
            if args[0] == "tesseract":
                Path(args[2] + ".txt").write_text(FRENCH_TITLE)
            return subprocess.CompletedProcess(args, 0, stdout=b"")

        with patch("logistique.import_title.subprocess.run", side_effect=run):
            self.assertEqual(len(extract_import_title(upload())["fields"]), 5)

    def test_rewinds_after_image_success(self):
        file = upload(b"image-data", name="titre.jpeg")
        with patch("logistique.import_title._image_text", return_value=FRENCH_TITLE):
            result = extract_import_title(file)
        self.assertEqual(len(result["fields"]), 5)
        self.assertEqual(file.tell(), 0)


if __name__ == "__main__":
    unittest.main()
