"""Safety-focused tests for deterministic document health observations."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.health_observation_service import extract_candidates


def test_extracts_named_value_with_unit_and_reference_range():
    rows = extract_candidates("Glucose 92 mg/dL 70 - 100")
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Glucose"
    assert row["value_numeric"] == 92
    assert row["unit"] == "mg/dL"
    assert (row["reference_low"], row["reference_high"]) == (70, 100)


def test_multiple_rows_keep_values_bound_to_their_own_test():
    rows = extract_candidates("Apolipoprotein B 46 mg/dL 46 - 174\nGlucose, Fasting 92 mg/dL 70 - 100\nHbA1c 5.4 % 4.0 - 5.6")
    by_name = {row["name"]: row for row in rows}
    assert by_name["Apolipoprotein B"]["value_numeric"] == 46
    assert by_name["Glucose"]["value_numeric"] == 92
    assert by_name["HbA1c"]["value_numeric"] == 5.4


def test_ambiguous_or_unrecognised_lines_are_not_saved_as_observations():
    # A number near a test word, but not in one verified row, is not evidence.
    assert extract_candidates("Apo B 46 mg/dL\nGlucose result pending") == []
    assert extract_candidates("Glucose 46") == []


def test_document_status_is_preserved_without_diagnosis():
    row = extract_candidates("LDL Cholesterol 118 mg/dL HIGH 0 - 100")[0]
    assert row["status"] == "HIGH"
    assert row["status_source"] == "DOCUMENT"
    assert row["category"] == "LIPID"


# ---------------------------------------------------------------------------
# Report layout support and status/ambiguity safety (from the phase requirements)
# ---------------------------------------------------------------------------

def test_table_layout_with_columns_is_parsed():
    """A 'Test Name | Results | Units | Ref' table must be parsed row by row."""
    text = (
        "Test Name   Results   Units   Bio. Ref. Interval\n"
        "Hemoglobin  13.5      g/dL    12-16\n"
        "Glucose     95        mg/dL   70-100\n"
        "Creatinine  0.9       mg/dL   0.6-1.3\n"
    )
    rows = extract_candidates(text)
    by_name = {r["name"]: r for r in rows}
    assert by_name["Hemoglobin"]["value_numeric"] == 13.5
    assert by_name["Hemoglobin"]["unit"] == "g/dL"
    assert (by_name["Hemoglobin"]["reference_low"], by_name["Hemoglobin"]["reference_high"]) == (12, 16)
    assert by_name["Glucose"]["value_numeric"] == 95
    assert by_name["Creatinine"]["value_numeric"] == 0.9
    assert by_name["Creatinine"]["category"] == "KIDNEY"


def test_multi_line_native_pdf_layout_is_bound_to_nearest_test():
    """Name on one line, value/unit/ref on the next (native PDF layout)."""
    text = (
        "APOLIPOPROTEIN B (Apo B)\n"
        "46.00 mg/dL 46 - 174\n"
        "LIPOPROTEIN(a); Lp(a), SERUM\n"
        "mg/dL <20\n"
    )
    rows = extract_candidates(text)
    by_name = {r["name"]: r for r in rows}
    assert by_name["Apolipoprotein B"]["value_numeric"] == 46.0
    # Below-detection inequality bound to the established Lp(a) name.
    assert by_name["Lipoprotein(a)"]["value_text"] == "<20"


def test_commentary_between_name_and_value_does_not_orphan_result():
    """hs-CRP: name line, 'Interpretation' header, then the value line."""
    text = (
        "CARDIO C-REACTIVE PROTEIN (hsCRP), SERUM\n"
        "Interpretation\n"
        "1.00 mg/L <1.00\n"
    )
    rows = extract_candidates(text)
    assert len(rows) == 1
    assert rows[0]["name"] == "hs-CRP"
    assert rows[0]["value_numeric"] == 1.0
    assert rows[0]["unit"] == "mg/L"


def test_abnormal_and_low_statuses_are_preserved():
    rows = extract_candidates(
        "ALT 88 U/L ABNORMAL 7 - 40\n"
        "Potassium 3.1 mmol/L LOW 3.5 - 5.1\n"
    )
    by_name = {r["name"]: r for r in rows}
    assert by_name["ALT"]["status"] == "ABNORMAL"
    assert by_name["Potassium"]["status"] == "LOW"


def test_ambiguous_inequality_in_single_line_is_rejected():
    """A '<200' that is a reference bound, not a patient value, must not be kept."""
    # 'Cholesterol  <200 mg/dL' is a reference upper bound -> ambiguous -> reject.
    rows = extract_candidates("Cholesterol  <200 mg/dL")
    assert rows == []


def test_unknown_test_or_missing_unit_is_not_fabricated():
    # Unrecognised test name.
    assert extract_candidates("Luteinizing Hormone 12.4 mIU/mL") == []
    # Numeric value with no unit is not reliable evidence.
    assert extract_candidates("Glucose 46") == []


def test_pipe_delimited_reference_tables_are_never_treated_as_results():
    """| HbA1c in % | 4.0-5.6 | 5.7-6.4 | >= 6.5 | must not become observations."""
    text = (
        "| HbA1c in %      | 4.0-5.6           | 5.7-6.4       | >= 6.5      | <7.0 |\n"
    )
    assert extract_candidates(text) == []
