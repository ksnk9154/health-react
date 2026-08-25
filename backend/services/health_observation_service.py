"""Deterministic extraction and retrieval of document-derived health observations.

The extractor only accepts a value when its known test name, numeric value, and
unit are confidently bound. It handles two common report layouts:

1. Single-line rows::

       Test Name   Result   Unit   Reference
       Hemoglobin  13.5     g/dL   12-16
       Glucose     95       mg/dL  70-100

2. Multi-line rows (common in generated/native PDFs), where the test name is on
   one line and the value/unit/reference appear on the following line::

       APOLIPOPROTEIN B (Apo B)
       46.00 ... mg/dL 46 - 174
       GLUCOSE, FASTING (F), PLASMA
       mg/dL 70 - 100

This deliberately favors missed values over assigning a neighbouring test's
value to the wrong observation: a numeric result binds to the name that most
recently precedes it, never to a different name.  It never uses the LLM and
never invents a result that is not present in the source text.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from db.models import HealthObservation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical test registry.
#
# Every known metric maps to a canonical display name + category.  Phrases that
# must appear as whole words in a name line are listed; the longest matching
# phrase wins so that "Total Cholesterol" outranks bare "Cholesterol".
# ---------------------------------------------------------------------------

# (canonical_name, category, (match phrases ...))
_TEST_REGISTRY = [
    # Diabetes / glucose
    ("HbA1c", "DIABETES", ("hba1c", "a1c", "glycated hemoglobin", "glycated haemoglobin")),
    ("Glucose", "GLUCOSE", ("glucose",)),
    # Lipids
    ("Total Cholesterol", "LIPID", ("total cholesterol",)),
    ("LDL Cholesterol", "LIPID", ("ldl cholesterol", "ldl-c", "ldl")),
    ("HDL Cholesterol", "LIPID", ("hdl cholesterol", "hdl-c", "hdl")),
    ("Triglycerides", "LIPID", ("triglyceride", "triglycerides")),
    ("Cholesterol", "LIPID", ("cholesterol",)),
    ("Lipoprotein(a)", "CARDIOVASCULAR", ("lipoprotein(a)", "lp(a)", "lipoprotein a")),
    ("Apolipoprotein B", "CARDIOVASCULAR", ("apolipoprotein b", "apolipoprotein")),
    ("hs-CRP", "CARDIOVASCULAR", ("c-reactive protein", "hscrp", "hs-crp")),
    # CBC
    ("Hemoglobin", "CBC", ("hemoglobin",)),
    ("WBC", "CBC", ("wbc", "white blood count", "white blood cell")),
    ("RBC", "CBC", ("rbc", "red blood count", "red blood cell")),
    ("Platelets", "CBC", ("platelet",)),
    ("Hematocrit", "CBC", ("hematocrit", "hct", "packed cell volume")),
    ("MCV", "CBC", ("mcv",)),
    ("MCH", "CBC", ("mch",)),
    # Kidney
    ("Creatinine", "KIDNEY", ("creatinine",)),
    ("Urea", "KIDNEY", ("urea", "bun", "blood urea nitrogen")),
    ("eGFR", "KIDNEY", ("egfr", "estimated gfr", "gfr")),
    ("Uric Acid", "KIDNEY", ("uric acid",)),
    # Liver
    ("ALT", "LIVER", ("alt", "sgpt", "alanine aminotransferase")),
    ("AST", "LIVER", ("ast", "sgot", "aspartate aminotransferase")),
    ("ALP", "LIVER", ("alp", "alkaline phosphatase")),
    ("Bilirubin", "LIVER", ("bilirubin",)),
    ("GGT", "LIVER", ("ggt", "gamma glutamyl", "gamma-gt")),
    ("LDH", "LIVER", ("ldh", "lactate dehydrogenase")),
    ("Total Protein", "LIVER", ("total protein",)),
    ("Albumin", "LIVER", ("albumin",)),
    # Thyroid
    ("TSH", "THYROID", ("tsh", "thyroid stimulating hormone")),
    ("T3", "THYROID", ("t3", "triiodothyronine")),
    ("T4", "THYROID", ("t4", "thyroxine")),
    ("Free T4", "THYROID", ("free t4",)),
    # Vitamins / minerals
    ("Vitamin D", "VITAMINS", ("vitamin d", "25-hydroxy", "25 oh vitamin d")),
    ("Vitamin B12", "VITAMINS", ("vitamin b12", "b12", "cobalamin")),
    ("Folate", "VITAMINS", ("folate", "folic acid")),
    ("Iron", "VITAMINS", ("iron",)),
    ("Ferritin", "VITAMINS", ("ferritin",)),
    # Electrolytes
    ("Sodium", "ELECTROLYTES", ("sodium",)),
    ("Potassium", "ELECTROLYTES", ("potassium",)),
    ("Chloride", "ELECTROLYTES", ("chloride",)),
    ("Calcium", "ELECTROLYTES", ("calcium",)),
    ("Bicarbonate", "ELECTROLYTES", ("bicarbonate",)),
    # Vitals / cardiovascular
    ("Blood Pressure", "VITALS", ("blood pressure",)),
    ("Heart Rate", "VITALS", ("heart rate", "pulse rate", "pulse")),
    ("Temperature", "VITALS", ("temperature",)),
    ("SpO2", "VITALS", ("spo2", "oxygen saturation", "o2 sat")),
    ("Weight", "WEIGHT", ("weight",)),
    ("Height", "VITALS", ("height",)),
    ("BMI", "VITALS", ("bmi",)),
]


def _match_test(name_text: str) -> Optional[tuple]:
    """Return (canonical_name, category) for the longest matching phrase.

    ``name_text`` and the registered phrases are normalized so that punctuation
    (commas, parentheses, the superscript in Lp(a)) does not block a match:
    "GLUCOSE, FASTING" still matches "glucose".
    """
    if not name_text:
        return None
    haystack = " " + _normalize_words(name_text) + " "
    best = None
    best_len = -1
    for canonical, category, phrases in _TEST_REGISTRY:
        for phrase in phrases:
            needle = " " + _normalize_words(phrase) + " "
            if needle in haystack and len(phrase) > best_len:
                best_len = len(phrase)
                best = (canonical, category)
    return best


def _normalize_words(text: str) -> str:
    """Lowercase and replace every non-alphanumeric char with a space."""
    return re.sub(r"[^a-zA-Z0-9]+", " ", text).lower()
_UNIT_RE = re.compile(
    r"^(mg/dL|g/dL|mmol/L|umol/L|ng/mL|pg/mL|ug/dL|ug/L|u/L|U/L|IU/mL|mIU/L|"
    r"mIU/mL|mEq/L|mmHg|mg/L|mL/min|L/min|%|kg|cm|kg/m2|bpm|ng/dl|u/dl|g/l)$",
    re.IGNORECASE,
)
_RANGE_RE = re.compile(
    r"(?P<low>\d+(?:[.,]\d+)?)\s*[-–—]\s*(?P<high>\d+(?:[.,]\d+)?)"
    r"|(?P<limit>[<>])\s*(?P<single>\d+(?:[.,]\d+)?)"
)
_NUMBER_RE = re.compile(r"^(?:<=|>=|<|>)?[+-]?\d+(?:[.,]\d+)?$")
_STATUS_WORDS = {
    "high": "HIGH", "higher": "HIGH", "elevated": "HIGH",
    "low": "LOW", "lower": "LOW",
    "abnormal": "ABNORMAL", "abn": "ABNORMAL",
    "normal": "NORMAL", "within range": "NORMAL", "in range": "NORMAL",
}


def _number(value: str) -> float:
    return float(value.replace(",", ".").lstrip("<>=+"))


def _page_for_line(text: str, line_index: int) -> Optional[int]:
    # PDF parser output uses form-feed separators where available.
    page = text[: sum(len(line) + 1 for line in text.splitlines()[:line_index])].count("\f") + 1
    return page if page > 0 else None


def _looks_like_commentary(line: str) -> bool:
    """Heuristic: narrative/reference-table lines that must never become observations."""
    low = line.lower()
    markers = (
        "comment", "interpretation", "reference", "risk", "diabetes", "myocardial",
        "infarction", "stroke", "coronary", "recommended", "persistent", "elevation",
        "correlate", "predictor", "cardiovascular", "trinity", "device", "prosthetic",
        "assess", "traditional", "healthy", "incident", "gingival",
    )
    return any(m in low for m in markers)
def _parse_row(line: str, allow_inequality: bool = False) -> Optional[dict]:
    """Parse a single observation row (name + value + unit + optional ref/status).

    Returns a dict or None.  Supports both "Name value unit ref" and the layout
    produced by the PDF parser where the numeric value and unit are adjacent.

    ``allow_inequality`` permits an inequality-only value (e.g. "<20").  In a
    self-contained single-line row such a value is indistinguishable from a
    reference bound (e.g. "Cholesterol  <200 mg/dL"), so it is rejected by
    default; when the test name has already been established on a prior line
    (pending binding) the inequality is a genuine "below detection" result.
    """
    line = line.strip()
    if not line or _looks_like_commentary(line):
        return None
    # Reject pipe-delimited rows: these are reference/risk/interpretation tables
    # (e.g. "| HbA1c in % | 4.0-5.6 | 5.7-6.4 | >= 6.5 |") and are NOT a single
    # patient observation.  A numeric value here must not become a fact.
    if "|" in line:
        return None
    # Skip column headers like "Test Name | Results | Units | Bio. Ref. Interval"
    if re.search(r"test\s+name", line, re.I) and re.search(r"result|unit", line, re.I):
        return None

    tokens = line.split()
    # Find the first numeric token that is a plausible value (not a range end).
    value_idx = None
    for i, tok in enumerate(tokens):
        if _NUMBER_RE.match(tok):
            next_tok = tokens[i + 1] if i + 1 < len(tokens) else None
            prev = tokens[i - 1] if i > 0 else None
            # Skip if part of a "low - high" range.
            if next_tok in ("-", "–", "—") and i + 2 < len(tokens) and _NUMBER_RE.match(tokens[i + 2]):
                continue
            if prev in ("-", "–", "—"):
                continue
            value_idx = i
            break
    if value_idx is None:
        return None

    # Name = everything before the value token.
    matched = _match_test(" ".join(tokens[:value_idx]))
    if not matched:
        return None
    canonical, category = matched

    try:
        value_numeric = _number(tokens[value_idx])
    except ValueError:
        return None
    value_text = tokens[value_idx]
    # In a single-line row, an inequality-only value is ambiguous (reference bound
    # vs below-detection) so it is rejected unless the name was already
    # established on a prior line (pending binding passes allow_inequality=True).
    if not allow_inequality and (value_text.startswith("<") or value_text.startswith(">")):
        return None

    # Unit: scan the whole row for a unit token (it may precede the value, as in
    # "mg/dL <20").  The value itself and range endpoints are not units.
    unit = None
    rest = tokens[value_idx + 1:]
    for tok in tokens:
        if tok == value_text:
            continue
        if _UNIT_RE.match(tok):
            unit = tok
            break
    # A numeric value without a unit is not reliable evidence (rejects "Glucose 46").
    if not unit:
        return None

    # Reference range + status from the remaining tokens.
    tail = " ".join(rest)
    reference_text = None
    low = high = None
    range_match = _RANGE_RE.search(tail)
    if range_match:
        reference_text = range_match.group(0).strip()
        if range_match.group("low"):
            low, high = _number(range_match.group("low")), _number(range_match.group("high"))
    status = "UNKNOWN"
    tail_lower = tail.lower()
    for word, mapped in _STATUS_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", tail_lower):
            status = mapped
            break

    return {
        "name": canonical, "category": category, "value_numeric": value_numeric,
        "value_text": value_text, "unit": unit,
        "reference_low": low, "reference_high": high, "reference_text": reference_text,
        "status": status, "status_source": "DOCUMENT", "confidence": "HIGH",
    }


def extract_candidates(text: str) -> list[dict]:
    """Return strictly validated candidates from layout-preserved extracted text.

    Two layout modes are handled:

    * Single-line rows where a known test name, value, and unit share one line.
    * Z615-style native PDF layout where the test name is printed on its own line
      and the numeric value/unit/reference follow on the next line.  A result is
      only accepted when the value line immediately follows a recognized name
      line, so a stray number can never be assigned to the wrong test.
    """
    candidates: list[dict] = []
    lines = text.splitlines()
    page = 1
    pending_name = None
    pending_page = None
    pending_source = None

    for idx, raw in enumerate(lines):
        if "\f" in raw:
            page += raw.count("\f")
        line = raw.strip()
        if not line:
            continue

        current_page = _page_for_line(text, idx) or page
        parsed = _parse_row(line)
        if parsed:
            parsed["source_page"] = current_page
            parsed["source_text"] = line
            candidates.append(parsed)
            pending_name = None
            continue

        if _looks_like_commentary(line):
            # Skip commentary / section-header lines (e.g. "Interpretation",
            # "Comments", "Note:") WITHOUT clearing the pending test name.
            # These headers frequently sit between a test-name line and its
            # value line on the following page of a lab report; clearing
            # pending_name here would orphan the value and miss the
            # observation (e.g. hs-CRP results).  The pending name is still
            # cleared by the next name-only line or a successful value bind.
            continue

        # Name-only line (known test, no value yet) -> bind to next value line.
        if _match_test(line) and not any(_NUMBER_RE.match(t) for t in line.split()):
            pending_name = _match_test(line)
            pending_page = current_page
            pending_source = line
            continue

        # A value/unit line with no name: bind to the pending name only when it
        # carries both a value and a unit (i.e., a real result, not a range row).
        # The test name was already established on the previous line, so an
        # inequality-only value (e.g. Lp(a) "<20") is a genuine below-detection
        # result here — allow it.
        if pending_name:
            parsed = _parse_row(f"{pending_name[0]} {line}", allow_inequality=True)
            if parsed:
                parsed["source_page"] = pending_page
                parsed["source_text"] = pending_source + " | " + line
                candidates.append(parsed)
            pending_name = None
            continue
        pending_name = None

    return candidates
def store_document_observations(session, document) -> int:
    """Replace this document's deterministic observations after successful parsing."""
    candidates = extract_candidates(document.extracted_text or "")
    existing = session.execute(select(HealthObservation).where(HealthObservation.document_id == document.id)).scalars().all()
    for observation in existing:
        session.delete(observation)
    now = datetime.now(timezone.utc).isoformat()
    for candidate in candidates:
        session.add(HealthObservation(user_id=document.user_id, document_id=document.id,
            observation_date=document.upload_time[:10] if document.upload_time else None,
            created_at=now, updated_at=now, **candidate))
    logger.info("Extracted %d validated health observations from document %d", len(candidates), document.id)
    return len(candidates)


def list_observations(user_ids, *, category=None, name=None, document_id=None, date_from=None, date_to=None, status=None):
    from db.session import get_db_session
    session = get_db_session()
    try:
        query = select(HealthObservation).where(HealthObservation.user_id.in_(user_ids))
        if category: query = query.where(HealthObservation.category == category.upper())
        if name: query = query.where(HealthObservation.name.ilike(f"%{name}%"))
        if status:
            statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
            if statuses:
                query = query.where(HealthObservation.status.in_(statuses))
        if document_id: query = query.where(HealthObservation.document_id == document_id)
        if date_from: query = query.where(HealthObservation.observation_date >= date_from)
        if date_to: query = query.where(HealthObservation.observation_date <= date_to)
        rows = session.execute(query.order_by(HealthObservation.observation_date.desc(), HealthObservation.id.desc())).scalars().all()
        return [serialize_observation(row) for row in rows]
    finally:
        session.close()


def serialize_observation(row):
    data = {column: getattr(row, column) for column in ("id", "user_id", "document_id", "observation_date", "category", "name", "value_numeric", "value_text", "unit", "reference_low", "reference_high", "reference_text", "status", "status_source", "confidence", "source_page", "source_text", "created_at", "updated_at")}
    data["document_name"] = row.document.original_filename if row.document else None
    return data