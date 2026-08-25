"""Integration tests for the deterministic document -> observation -> overview flow.

These validate that:
  - source provenance (document filename, page) reaches alerts/comparisons/trends
  - trends are only produced when a metric has repeated observations
  - user data isolation is enforced end to end
  - list_observations supports status/name/category/document_id filters
  - OCR extension point never fabricates results when disabled
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:?foreign_keys=on")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from db.session import get_db_session, engine
from db.models import Base, User, Document, HealthObservation, HealthRecord
from services.health_intelligence import build_overview
from services.health_observation_service import list_observations


@pytest.fixture(scope="module", autouse=True)
def seed_database():
    """Create the schema and seed two scoped users with source documents."""
    Base.metadata.create_all(bind=engine)
    session = get_db_session()
    try:
        u1 = User(username="intel_user_a", password_hash="x", role="User")
        u2 = User(username="intel_user_b", password_hash="x", role="User")
        session.add_all([u1, u2])
        session.commit()

        doc_a = Document(
            user_id=u1.id, original_filename="jan_lab_report.pdf",
            stored_filename="jan_lab_report.pdf", mime_type="application/pdf",
            file_size=1024, checksum="aa", version=1,
            upload_time="2026-01-01T00:00:00", created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00", status="PROCESSED",
        )
        doc_b = Document(
            user_id=u1.id, original_filename="feb_lab_report.pdf",
            stored_filename="feb_lab_report.pdf", mime_type="application/pdf",
            file_size=1024, checksum="bb", version=1,
            upload_time="2026-02-01T00:00:00", created_at="2026-02-01T00:00:00",
            updated_at="2026-02-01T00:00:00", status="PROCESSED",
        )
        session.add_all([doc_a, doc_b])
        session.commit()

        now = "2026-02-01T00:00:00Z"
        session.add_all([
            # u1: glucose repeated across two documents (Jan normal, Feb high).
            HealthObservation(user_id=u1.id, document_id=doc_a.id, observation_date="2026-01-05",
                              category="GLUCOSE", name="Glucose", value_numeric=96, value_text="96",
                              unit="mg/dL", reference_low=70, reference_high=100,
                              status="NORMAL", status_source="DOCUMENT", confidence="HIGH",
                              source_page=1, source_text="Glucose 96 mg/dL 70 - 100", created_at=now, updated_at=now),
            HealthObservation(user_id=u1.id, document_id=doc_b.id, observation_date="2026-02-05",
                              category="GLUCOSE", name="Glucose", value_numeric=118, value_text="118",
                              unit="mg/dL", reference_low=70, reference_high=100,
                              status="HIGH", status_source="DOCUMENT", confidence="HIGH",
                              source_page=2, source_text="Glucose 118 mg/dL HIGH 70 - 100", created_at=now, updated_at=now),
            # Single-metric value: must not appear in trends (insufficient data).
            HealthObservation(user_id=u1.id, document_id=doc_a.id, observation_date="2026-01-05",
                              category="VITALS", name="SpO2", value_numeric=98, value_text="98",
                              unit="%", status="NORMAL", status_source="DOCUMENT", confidence="HIGH",
                              source_page=1, source_text="SpO2 98 %", created_at=now, updated_at=now),
        ])
        session.commit()
        session.add(HealthRecord(user_id=u1.id, record_date="2026-01-10", weight_kg=80.0))
        session.commit()
        return {"u1": u1.id, "u2": u2.id, "doc_a": doc_a.id, "doc_b": doc_b.id}
    finally:
        session.close()


def test_overview_alerts_carry_document_provenance(seed_database):
    overview = build_overview([seed_database["u1"]])
    alerts = overview["alerts"]
    alert = next((a for a in alerts if "reported as high" in a["title"]), None)
    assert alert is not None, "expected a HIGH alert for the Feb glucose report"
    assert alert["document_id"] == seed_database["doc_b"]
    assert alert["document_name"] == "feb_lab_report.pdf"
    assert alert["source_page"] == 2
    assert alert["date"] == "2026-02-05"
    assert "Glucose" in alert["title"]


def test_overview_trends_only_include_repeated_metrics(seed_database):
    overview = build_overview([seed_database["u1"]])
    trends = overview["trends"]
    assert "Glucose" in trends, "glucose has two results so should be chartable"
    assert len(trends["Glucose"]) == 2
    assert trends["Glucose"][0]["document_name"] == "jan_lab_report.pdf"
    assert trends["Glucose"][1]["document_name"] == "feb_lab_report.pdf"
    assert trends["Glucose"][0]["value"] == 96
    assert trends["Glucose"][0]["source_page"] == 1
    # Single-result metric is not chartable.
    assert "SpO2" not in trends


def test_overview_comparisons_include_provenance(seed_database):
    overview = build_overview([seed_database["u1"]])
    comparisons = [c for c in overview["comparisons"] if c["name"] == "Glucose"]
    assert len(comparisons) == 1
    comp = comparisons[0]
    assert comp["previous"] == 96 and comp["current"] == 118 and comp["change"] == 22
    assert comp["previous_document_name"] == "jan_lab_report.pdf"
    assert comp["document_name"] == "feb_lab_report.pdf"


def test_user_scope_is_isolated(seed_database):
    # u2 has no observations/documents, so an overview should be empty of alerts.
    overview = build_overview([seed_database["u2"]])
    assert overview["alerts"] == []
    assert overview["trends"] == {}
    assert overview["comparisons"] == []
    assert overview["metrics"]["observation_count"] == 0


def test_list_observations_filters_and_isolates(seed_database):
    u1_rows = list_observations([seed_database["u1"]])
    names = {r["name"] for r in u1_rows}
    assert names == {"Glucose", "SpO2"}
    assert all(r["document_name"] for r in u1_rows), "every row should carry source filename"

    # Status filter returns only the flagged high observation.
    high = list_observations([seed_database["u1"]], status="HIGH")
    assert len(high) == 1 and high[0]["name"] == "Glucose" and high[0]["status"] == "HIGH"

    # Name + category filter.
    filtered = list_observations([seed_database["u1"]], name="glucose", category="GLUCOSE")
    assert {r["name"] for r in filtered} == {"Glucose"}

    # Document filter.
    by_doc = list_observations([seed_database["u1"]], document_id=seed_database["doc_a"])
    assert {r["name"] for r in by_doc} == {"Glucose", "SpO2"}

    # Other user cannot see u1's rows.
    assert list_observations([seed_database["u2"]]) == []

    # No observation filters return no data (never a panic).
    assert list_observations([seed_database["u1"]], status="ABNORMAL") == []
    assert list_observations([seed_database["u1"]], name="nonexistent") == []


def test_ocr_extension_is_non_invasive():
    from services.ocr_extension import is_ocr_enabled, is_ocr_available, ocr_extract_text, OCR_EXTENSIONS
    assert is_ocr_enabled() is False, "OCR must be disabled by default"
    assert is_ocr_available() is False, "OCR should report unavailable without opt-in"
    assert ".png" in OCR_EXTENSIONS
    # Without OCR enabled, no fake text is ever returned.
    assert ocr_extract_text("/tmp/never.png", ".png") is None
# ---------------------------------------------------------------------------
# Full pipeline: document -> parse -> extract_candidates -> store -> overview
# ---------------------------------------------------------------------------

_REPORT_TEXT = """Page 1 of 2
Test Name   Results   Units   Bio. Ref. Interval
Hemoglobin  13.5      g/dL    12-16
Glucose     95        mg/dL   70-100
LDL Cholesterol  118  mg/dL  HIGH  0-100
Creatinine 0.9   mg/dL  0.6-1.3

CARDIO C-REACTIVE PROTEIN (hsCRP), SERUM
Interpretation
1.00 mg/L <1.00

APOLIPOPROTEIN B (Apo B)
46.00 mg/dL 46 - 174
GLUCOSE, FASTING (F), PLASMA
mg/dL 70 - 100
"""


def test_document_to_observation_to_overview_pipeline(seed_database):
    """The complete deterministic flow must yield stored, source-attributed data."""
    session = get_db_session()
    try:
        doc = Document(
            user_id=seed_database["u1"],
            original_filename="Z615-report.pdf",
            stored_filename="z615.pdf", mime_type="application/pdf",
            file_size=2048, checksum="zz", version=1,
            upload_time="2026-03-01T00:00:00", created_at="2026-03-01T00:00:00",
            updated_at="2026-03-01T00:00:00", status="READY",
            extracted_text=_REPORT_TEXT,
        )
        session.add(doc)
        session.commit()

        from services.health_observation_service import store_document_observations
        count = store_document_observations(session, doc)
        session.commit()
        assert count >= 5, f"Expected >= 5 verified observations, got {count}"

        from services.health_observation_service import list_observations
        rows = list_observations([seed_database["u1"]], document_id=doc.id)
        assert len(rows) == count
        by_name = {r["name"]: r for r in rows}
        for r in rows:
            assert r["document_id"] == doc.id
            assert r["document_name"] == "Z615-report.pdf"
        assert by_name["LDL Cholesterol"]["status"] == "HIGH"
        assert by_name["LDL Cholesterol"]["status_source"] == "DOCUMENT"
        assert by_name["Glucose"]["value_numeric"] == 95

        overview = build_overview([seed_database["u1"]])
        alert_titles = {a["title"] for a in overview["alerts"]}
        assert any("ldl cholesterol" in t.lower() for t in alert_titles)
        assert overview["metrics"]["observation_count"] >= count
        cats = [c["name"] for c in overview["categories"].get("LIPID", [])]
        assert "LDL Cholesterol" in cats
    finally:
        session.close()


def test_llm_health_context_contains_verified_observations(seed_database):
    """The LLM context must carry verified observations with document provenance."""
    session = get_db_session()
    try:
        doc = Document(
            user_id=seed_database["u1"],
            original_filename="Z615-report.pdf",
            stored_filename="z615.pdf", mime_type="application/pdf",
            file_size=2048, checksum="zz2", version=1,
            upload_time="2026-03-01T00:00:00", created_at="2026-03-01T00:00:00",
            updated_at="2026-03-01T00:00:00", status="READY",
            extracted_text=_REPORT_TEXT,
        )
        session.add(doc)
        session.commit()
        from services.health_observation_service import store_document_observations
        count = store_document_observations(session, doc)
        session.commit()
        assert count >= 5
    finally:
        session.close()

    from api.routes.llm import _build_health_context
    ctx = _build_health_context({"id": seed_database["u1"], "role": "User"}, limit=20)
    assert "Recent verified document observations" in ctx
    assert "Glucose" in ctx
    assert "Z615-report.pdf" in ctx, "LLM context should cite the source document filename"
    assert "LDL Cholesterol" in ctx


def test_backfill_ready_document_recomputes_observations(seed_database):
    """A READY document with text but stale/missing observations gets backfilled."""
    session = get_db_session()
    try:
        doc = Document(
            user_id=seed_database["u1"],
            original_filename="backfilled.pdf",
            stored_filename="backfilled.pdf", mime_type="application/pdf",
            file_size=1024, checksum="bf", version=1,
            upload_time="2026-04-01T00:00:00", created_at="2026-04-01T00:00:00",
            updated_at="2026-04-01T00:00:00", status="READY",
            extracted_text=_REPORT_TEXT,
            doc_metadata='{"word_count": 200}',
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id
    finally:
        session.close()

    class FakeTasks:
        def add_task(self, fn, *args, **kwargs):
            fn(*args, **kwargs)

    from services.document_service import extract_document
    result = extract_document(doc_id, seed_database["u1"], FakeTasks())
    assert result["success"] is True
    assert result["data"]["observation_count"] > 0, \
        "READY document with extractable text must have observations backfilled"

    session = get_db_session()
    try:
        rows = list_observations([seed_database["u1"]], document_id=doc_id)
        assert len(rows) > 0
        assert rows[0]["document_name"] == "backfilled.pdf"
    finally:
        session.close()


def test_llm_context_distinguishes_documents_without_observations(seed_database):
    """A user with documents but no verified observations gets a helpful message.

    Regression guard: 'Analyze My Health Data' previously returned a flat
    'no observations' line, hiding that a report was present but not converted
    into structured measurements.
    """
    session = get_db_session()
    try:
        doc = Document(
            user_id=seed_database["u2"],
            original_filename="nonlab_report.pdf",
            stored_filename="nonlab_report.pdf", mime_type="application/pdf",
            file_size=512, checksum="n0lab", version=1,
            upload_time="2026-05-01T00:00:00", created_at="2026-05-01T00:00:00",
            updated_at="2026-05-01T00:00:00", status="READY",
            extracted_text="Patient is doing well. No laboratory values in this note.",
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id
        from services.health_observation_service import store_document_observations
        stored = store_document_observations(session, doc)
        session.commit()
    finally:
        session.close()

        # Sanity: no observations materialized from non-lab text, but the doc exists.
    assert list_observations([seed_database["u2"]], document_id=doc_id) == []

    from api.routes.llm import _build_health_context
    ctx = _build_health_context({"id": seed_database["u2"], "role": "User"}, limit=10)
    assert "uploaded document" in ctx.lower()
    assert "re-extract" in ctx.lower()
    # Must NOT claim there are no documents at all.
    assert "Upload a health report" not in ctx


def test_llm_context_no_documents_gets_generic_message(seed_database):
    """A user with nothing uploaded at all gets the generic empty-state message."""
    session = get_db_session()
    try:
        fresh = User(username="empty_user_ctx", password_hash="x", role="User")
        session.add(fresh)
        session.commit()
        uid = fresh.id
    finally:
        session.close()

    from api.routes.llm import _build_health_context
    ctx = _build_health_context({"id": uid, "role": "User"}, limit=10)
    assert "No health records" in ctx


def test_llm_context_attribution_uses_document_filename():
    """Observation lines cite the source document filename, not a raw id."""
    from api.routes.llm import _append_observation_line
    obs = {
        "document_id": 4242,
        "document_name": "my-lab-report.pdf",
        "name": "Glucose",
        "value_text": "95",
        "value_numeric": None,
        "unit": "mg/dL",
        "reference_text": "70-100",
        "source_page": 2,
        "status": "NORMAL",
        "confidence": "HIGH",
    }
    lines = []
    _append_observation_line(lines, obs)
    assert lines[-1].startswith("Glucose: 95 mg/dL")
    assert "my-lab-report.pdf" in lines[-1]
    assert "page 2" in lines[-1]
    assert "Reference: 70-100" in lines[-1]
    # Falls back to stored document id when no filename present.
    obs2 = dict(obs)
    obs2["document_name"] = None
    lines2 = []
    _append_observation_line(lines2, obs2)
    assert "document_id=4242" in lines2[-1]
