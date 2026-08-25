"""Structured lab-report extraction (deterministic, LLM-independent).

This module exists to prevent the class of bug where the LLM "decides" which
number belongs to which test:

    Glucose = 46 mg/dL   (actually ApoB's value)   -> hallucinated
    Lp(a)   = 46 mg/dL                            -> hallucinated
    "The patient has Diabetes."                     -> hallucinated

The core safety invariant: a numeric result is bound ONLY to the test-name
line that most recently precedes it in the document flow, so a value from
"Test A" can NEVER appear as "Test B"'s result. When a result cannot be
reliably associated with a test (e.g. only a reference range is present, or the
value token is ambiguous), the extractor reports the result as
``(not clearly present in the document)`` instead of guessing.

Works on layout-preserved text from services.parsers.pdf_parser. Never calls an LLM.
"""

import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


# A numeric result token, optionally bounded by an inequality marker.
# Matches: 46.00, 1.00, 88, <20, <1.00, >=125, 7.2
_NUMBER_RE = re.compile(r"^[<>=~]?[+-]?\d+(?:[.,]\d+)?[<>]?$")

# Medical units commonly found in serum/urine lab panels.
_UNIT_WORD_RE = re.compile(
    r"^(?:mg/dL|mg/L|mg%|g/dL|g/L|mmol/L|umol/L|nmol/L|µmol/L|ug/L|ng/mL|"
    r"pg/mL|u/L|U/L|kU/L|mEq/L|mmol|mEq|mmHg|mol/L|mIU|uMol|10\^9/L|cells/uL|"
    r"mcg/L|ng/dL|mg/100mL)$",
    re.IGNORECASE,
)

# Narrative / reference-table lines that must NOT be mistaken for test names.
_COMMENTARY_KEYWORDS = {
    "diabetes", "correlates", "myocardial", "infarction", "stroke", "powerful",
    "strongest", "predictor", "prediction", "incident", "healthy", "traditional",
    "risk", "significant", "assessment", "improves", "assess", "recommended",
    "recommend", "comment", "interpretation", "calculate", "average",
    "persistent", "elevation", "cardiovascular", "trinity", "device",
    "prosthetic", "note", "cardio crp", "cardiovascular risk",
    "non cardiovascular",
}

_KNOWN_TEST_KEYWORDS = [
    "glucose", "cholesterol", "ldl", "hdl", "triglyceride", "apolipoprotein",
    "lipoprotein", "crp", "c-reactive", "creatinine", "urea", "bilirubin",
    "alt", "ast", "alp", "ggt", "ldh", "hba1c", "tsh", "t4", "t3",
    "vitamin", "b12", "folate", "iron", "ferritin", "tibc", "transferrin",
    "uric", "phosphorus",
]


def _is_unit_token(token: str) -> bool:
    if _UNIT_WORD_RE.match(token):
        return True
    # Tokens like "mg/dL", "ng/mL" contain '/' and look like units.
    if "/" in token and re.match(r"^[a-zA-Z][a-zA-Z0-9/µ<>]*$", token) and len(token) >= 2:
        return True
    return False


def _is_number_token(token: str) -> bool:
    """True for a numeric result/limit token (number, possibly with < >=)."""
    if not _NUMBER_RE.match(token):
        return False
    return any(ch.isdigit() for ch in token)


def _is_range_at(tokens: list, i: int) -> bool:
    """True if tokens[i] starts a reference range like '70 - 100'."""
    if i + 2 >= len(tokens):
        return False
    if not _is_number_token(tokens[i]):
        return False
    if tokens[i + 1] not in ("-", "–", "—"):
        return False
    if not _is_number_token(tokens[i + 2]):
        return False
    return True


def _looks_like_commentary(line: str, tokens: list) -> bool:
    """Heuristic: a narrative / reference-table line, NOT a test name."""
    low = line.strip().lower()
    if "|" in line:  # bordered reference table (e.g. hsCRP risk strata)
        return True
    if re.fullmatch(r"[\s\-_=.~*]+", line):  # a separator line
        return True
    for kw in _COMMENTARY_KEYWORDS:
        if kw in low:
            return True
    return False


def _looks_like_test_name_line(line: str, tokens: list) -> bool:
    """A line that names a lab test and carries NO numeric result of its own.

    Real lab test header lines contain punctuation/markers (parentheses, comma,
    semicolon, or a body-fluid word) and no numeric token. Narrative lines such
    as "Diabetes." or risk words such as "High"/"Average" lack those markers and
    are excluded via _looks_like_commentary().
    """
    if not tokens:
        return False
    if any(_is_number_token(t) for t in tokens):
        return False
    if _looks_like_commentary(line, tokens):
        return False
    if not any(re.search(r"[A-Za-z]", t) for t in tokens):
        return False
    joined = " ".join(tokens)
    if any(ch in joined for ch in "(),;"):
        return True
    if re.search(r"\b(SERUM|PLASMA|URINE|BLOOD)\b", joined, re.I):
        return True
    for kw in _KNOWN_TEST_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", joined, re.I):
            return True
    return False


def _extract_row_from_line(tokens: list) -> Optional[Dict[str, str]]:
    """Parse a single data line that may contain name+value+unit+ref.

    Returns a row dict or None if the line has no parseable number token.
    A result is NEVER taken from a range token (those are reference intervals).
    """
    if not tokens:
        return None

    # Locate a reference range expression "x - y" (e.g. '70 - 100', '46 - 174').
    range_str = None
    range_set = set()  # token indices that belong to the range
    for i, t in enumerate(tokens):
        if _is_range_at(tokens, i):
            range_str = f"{tokens[i]} - {tokens[i + 2]}"
            range_set.update({i, i + 1, i + 2})
            break  # use the first range on the line

    # Result = first numeric token NOT part of a range expression.
    result_idx = None
    for i, t in enumerate(tokens):
        if not _is_number_token(t):
            continue
        if i in range_set:
            continue
        result_idx = i
        break

    if result_idx is None:
        return None  # no patient result on this line (e.g. "mg/dL 70 - 100")

    result_value = tokens[result_idx]

    # Unit = first unit token anywhere on the line.
    unit_idx = None
    for i, t in enumerate(tokens):
        if _is_unit_token(t):
            unit_idx = i
            break
    unit = (
        tokens[unit_idx]
        if unit_idx is not None
        else "(not clearly present in the document)"
    )

    # Reference interval = explicit range if present, otherwise a '<'/'>' limit
    # token that is NOT the result token (e.g. '<1.00' on the hsCRP line).
    ref = range_str
    if not ref:
        limit_tokens = []
        for i, t in enumerate(tokens):
            if i == result_idx or i in range_set or i == unit_idx:
                continue
            if _is_number_token(t) and (t.startswith("<") or t.startswith(">")):
                limit_tokens.append(t)
        if limit_tokens:
            ref = " ".join(limit_tokens)
    if not ref:
        ref = "(not clearly present in the document)"

    # Test name = leading alphabetic tokens (only when embedded on one line).
    name_tokens = []
    for t in tokens:
        if _is_number_token(t) or _is_unit_token(t):
            break
        name_tokens.append(t)
    test_name = " ".join(name_tokens).strip()

    return {
        "test_name": test_name,
        "result": result_value,
        "unit": unit,
        "reference_interval": ref,
        "source": "document",
        "confidence": "high",
    }


def extract_lab_results(text: str) -> List[Dict[str, str]]:
    """Extract structured lab results from layout-preserved document text.

    Safety invariant: a numeric result binds ONLY to the test-name line that
    most recently precedes it, so a value from Test A can NEVER appear as
    Test B's result. When no reliable result can be associated, the result is
    reported as "(not clearly present in the document)" rather than invented.
    """
    if not text:
        return []

    rows: List[Dict[str, str]] = []
    pending_name: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        tokens = line.split()
        if not tokens:
            continue

        # Skip the column header row: "Test Name | Results | Units | Bio. Ref. Interval"
        if "Test Name" in line and "Results" in line and "Unit" in line:
            continue

        commentary = _looks_like_commentary(line, tokens)
        is_name = _looks_like_test_name_line(line, tokens)
        line_has_number = any(_is_number_token(t) for t in tokens)

        if is_name and not line_has_number:
            pending_name = " ".join(tokens).strip()
            continue

        parsed = _extract_row_from_line(tokens)
        if parsed is None:
            if commentary:
                continue
            # Unit+range-only lines (e.g. "mg/dL 70 - 100") attach to pending name
            # as "result not clearly present" once we see a subsequent name/end.
            if pending_name and any(_is_unit_token(t) for t in tokens):
                # Capture unit/ref even when patient result is missing.
                unit = next((t for t in tokens if _is_unit_token(t)), "")
                range_str = ""
                for i, t in enumerate(tokens):
                    if _is_range_at(tokens, i):
                        range_str = f"{tokens[i]} - {tokens[i + 2]}"
                        break
                rows.append({
                    "test_name": pending_name,
                    "result": "(not clearly present in the document)",
                    "unit": unit or "(not clearly present in the document)",
                    "reference_interval": range_str or "(not clearly present in the document)",
                    "source": "document",
                    "confidence": "low",
                })
                pending_name = None
            continue

        if pending_name:
            parsed["test_name"] = pending_name
        elif not parsed["test_name"]:
            parsed["test_name"] = "(not clearly present in the document)"
        pending_name = None
        rows.append(parsed)

    if pending_name:
        rows.append({
            "test_name": pending_name,
            "result": "(not clearly present in the document)",
            "unit": "",
            "reference_interval": "",
            "source": "document",
            "confidence": "low",
        })

    logger.debug("lab_extractor: extracted %d structured lab rows", len(rows))
    return rows


def format_lab_table(rows: List[Dict[str, str]]) -> str:
    """Render structured lab rows as a markdown table (for prompt injection)."""
    if not rows:
        return "(no verified lab results detected in the document)"
    header = "| Test | Result | Unit | Reference Interval |\n|---|---|---|---|\n"
    body = "".join(
        f"| {r['test_name']} | {r['result']} | {r.get('unit', '')} "
        f"| {r.get('reference_interval', '')} |\n"
        for r in rows
    )
    return header + body
