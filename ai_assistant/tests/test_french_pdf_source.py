import pytest

from ai_assistant.french_pdf import split_french_sources
from ai_assistant.pdf_translation import source


def test_french_pdf_retains_invoice_labels_and_protected_values_exactly():
    values = ["Location STORE N° 42", "Pièce", "• Livrer avant midi.\n• Marbre non compris.", "1 200 MAD"]
    originals, foreign = split_french_sources([source(value) for value in values])

    assert originals == {value: value for value in values}
    assert foreign == []


@pytest.mark.parametrize("text", [
    "Payment is due upon receipt.",
    "Betaling binnen dertig dagen.",
    "Lieferung und Montage",
    "Livrer avant midi.\nPayment is due upon receipt.",
])
def test_clearly_foreign_fields_still_require_translation(text):
    spec = source(text)
    originals, foreign = split_french_sources([spec])

    assert originals == {}
    assert foreign == [spec]
