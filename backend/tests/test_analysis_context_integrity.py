"""Regression tests for document-analysis context integrity.

Guards against the class of bug where the LLM receives unrelated/garbage
text (e.g. PUA-encoded PDF glyphs) or chunks from the wrong document, which
produced wildly inaccurate summaries for the same PDF.

These tests exercise the real AnalysisService pipeline with a fully mocked
session + fake LLM, so they never touch the real database or network.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.analysis_service import analysis_service  # noqa: E402
from services.parsers.pdf_parser import _fix_pua_encoded_text  # noqa: E402
from services.prompt_builder import prompt_builder  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeResult:
    """Mimics sqlalchemy Result enough for `.scalar_one_or_none()`."""

    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def scalar(self):
        return self._obj

    def scalars(self):
        class _S:
            def __init__(self, obj):
                self._obj = obj

            def all(self):
                return [self._obj] if self._obj else []

            def first(self):
                return self._obj

        return _S(self._obj)

    def all(self):
        return [self._obj] if self._obj else []

    def first(self):
        return self._obj


class FakeSession:
    """Session that always returns the configured document from execute()."""

    def __init__(self, doc):
        self._doc = doc
        self.added = []

    def execute(self, stmt, *a, **k):
        return FakeResult(self._doc)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1

    def rollback(self):
        pass

    def close(self):
        pass


class FakeDocument:
    """Minimal stand-in for the Document model."""

    def __init__(self, doc_id, filename, text, chunk_texts=None, page_count=1):
        self.id = doc_id
        self.user_id = 1
        self.original_filename = filename
        self.stored_filename = f"stored-{doc_id}.pdf"
        self.status = "READY"
        self.extracted_text = text
        self.doc_metadata = json.dumps({"pages": page_count, "word_count": len(text.split())})
        if chunk_texts is None:
            chunk_texts = [text]
        chunks = [
            {
                "chunk_index": i,
                "page_number": min(i + 1, page_count),
                "start_word": 0,
                "end_word": len(ct.split()) - 1,
                "text": ct,
            }
            for i, ct in enumerate(chunk_texts)
        ]
        self.text_chunks = json.dumps(chunks)


class FakeLLM:
    """Records the messages sent to the LLM; returns a fixed reply."""

    def __init__(self, reply="Document summary completed."):
        self.reply = reply
        self.calls = []

    async def chat_async(self, messages, model=None, stream=False):
        self.calls.append({"messages": messages, "model": model, "stream": stream})
        if stream:
            async def gen():
                yield self.reply

            return gen()
        return self.reply


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def patched_pipeline(monkeypatch, fake_llm):
    """Patch session + LLM + cache/filter/citations so analyze runs offline."""
    current_doc = {}

    def fake_get_db_session():
        return FakeSession(current_doc["doc"])

    monkeypatch.setattr("services.analysis_service.get_db_session", fake_get_db_session)
    monkeypatch.setattr(analysis_service, "llm", fake_llm)
    monkeypatch.setattr(analysis_service, "citation_generator", _FakeCitations())
    monkeypatch.setattr(analysis_service, "context_selector", _FakeSelector())
    monkeypatch.setattr("services.analysis_service.output_filter", _FakeOutputFilter())
    monkeypatch.setattr(analysis_service.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(analysis_service.cache, "set", lambda *a, **k: None)

    def _set(doc):
        current_doc["doc"] = doc

    _set(FakeDocument(1, "alpha.pdf", "ALPHA-ONLY lab report about heart health screen."))
    return _set


class _FakeCitations:
    def generate_citations(self, chunks, response):
        return []


class _FakeSelector:
    """Return all chunks so the prompt contains the full document context."""

    def select_chunks(self, analysis_type, chunks, max_tokens=4000, question=None):
        return chunks


class _FakeOutputFilter:
    def filter_response(self, response, analysis_type, source_text):
        return {
            "content": response,
            "warnings": [],
            "system_prompt_leaked": False,
            "disclaimer_added": False,
        }


# ---------------------------------------------------------------------------
# PDF parser PUA decoding
# ---------------------------------------------------------------------------

def test_pdf_pua_decode_known_report():
    """PUA-encoded glyphs (0xF000|ASCII) must decode to real ASCII."""
    raw = "\uf052\uf065\uf070\uf06f\uf072\uf074"  # "Report"
    assert _fix_pua_encoded_text(raw) == "Report"


def test_pdf_pua_decode_full_sentence():
    raw = (
        "\uf048\uf065\uf061\uf072\uf074\uf020\uf048\uf065\uf061\uf06c\uf074\uf068"
    )  # "Heart Health"
    assert _fix_pua_encoded_text(raw) == "Heart Health"


def test_pdf_pua_decode_leaves_normal_text_and_punctuation():
    assert _fix_pua_encoded_text("Plain ASCII text 123.") == "Plain ASCII text 123."
    assert _fix_pua_encoded_text("") == ""
    # Non-printable PUA low bytes are left untouched.
    assert _fix_pua_encoded_text("\uf0a0") == "\uf0a0"


# ---------------------------------------------------------------------------
# Context integrity (prompt = only the requested document's text)
# ---------------------------------------------------------------------------

async def _run_summary_async(fake_llm, doc):
    """Run a real analyze_document() call and return the captured prompts."""
    fake_llm.calls.clear()
    await analysis_service.analyze_document(
        document_id=doc.id,
        analysis_type="summary",
        user_id=1,
    )
    assert fake_llm.calls, "LLM should have been called"
    messages = fake_llm.calls[-1]["messages"]
    user_prompt = [m["content"] for m in messages if m["role"] == "user"][0]
    system_prompt = [m["content"] for m in messages if m["role"] == "system"][0]
    return user_prompt, system_prompt


def _run_summary(fake_llm, doc):
    import asyncio
    return asyncio.run(_run_summary_async(fake_llm, doc))


def test_analysis_uses_only_requested_documents_text(patched_pipeline, fake_llm):
    """Doc A's summary prompt must contain A's text and never B's text."""
    doc_a = FakeDocument(
        1,
        "alpha.pdf",
        "ALPHA-ONLY-CONTENT heart health screen apolipoprotein glucose.",
        chunk_texts=["ALPHA-ONLY-CONTENT heart health screen apolipoprotein glucose."],
    )
    patched_pipeline(doc_a)
    user_prompt, _ = _run_summary(fake_llm, doc_a)

    assert "ALPHA-ONLY-CONTENT" in user_prompt
    assert "BETA-ONLY-CONTENT" not in user_prompt


def test_analysis_chunks_belong_to_requested_document(patched_pipeline, fake_llm):
    """Each document's analysis uses ONLY that document's chunks."""
    doc_a = FakeDocument(
        1,
        "alpha.pdf",
        "ALPHA-ONLY-CONTENT alpha segment one. alpha segment two.",
        chunk_texts=["ALPHA-ONLY-CONTENT alpha segment one.", "alpha segment two."],
    )
    doc_b = FakeDocument(
        2,
        "beta.pdf",
        "BETA-ONLY-CONTENT beta segment one. beta segment two.",
        chunk_texts=["BETA-ONLY-CONTENT beta segment one.", "beta segment two."],
    )

    patched_pipeline(doc_a)
    user_prompt_a, _ = _run_summary(fake_llm, doc_a)
    assert "ALPHA-ONLY-CONTENT" in user_prompt_a
    assert "BETA-ONLY-CONTENT" not in user_prompt_a

    patched_pipeline(doc_b)
    user_prompt_b, _ = _run_summary(fake_llm, doc_b)
    assert "BETA-ONLY-CONTENT" in user_prompt_b
    assert "ALPHA-ONLY-CONTENT" not in user_prompt_b


def test_analysis_prompt_contains_actual_document_context(patched_pipeline, fake_llm):
    """The final user prompt embeds the document's real extracted text."""
    text = "TROPONIN-I SERUM HIGH SENSITIVE CMIA ng/L 4 and LIPID PROFILE BASIC."
    doc = FakeDocument(1, "lab.pdf", text, chunk_texts=[text])
    patched_pipeline(doc)
    user_prompt, _ = _run_summary(fake_llm, doc)

    # Sanitization strips control chars only; real words must survive.
    assert "TROPONIN-I" in user_prompt
    assert "LIPID PROFILE" in user_prompt


def test_no_stale_analysis_between_documents(patched_pipeline, fake_llm):
    """Analyzing doc B must never reuse doc A's prompt/analysis content."""
    doc_a = FakeDocument(1, "alpha.pdf", "ALPHA-ONLY-CONTENT alpha heartbeat summary.")
    doc_b = FakeDocument(2, "beta.pdf", "BETA-ONLY-CONTENT beta cholesterol summary.")

    patched_pipeline(doc_a)
    _run_summary(fake_llm, doc_a)
    first_prompt = [m["content"] for m in fake_llm.calls[-1]["messages"] if m["role"] == "user"][0]

    patched_pipeline(doc_b)
    _run_summary(fake_llm, doc_b)
    second_prompt = [m["content"] for m in fake_llm.calls[-1]["messages"] if m["role"] == "user"][0]

    assert first_prompt != second_prompt
    assert "ALPHA-ONLY-CONTENT" in first_prompt
    assert "BETA-ONLY-CONTENT" in second_prompt


def test_system_prompt_instructs_source_only_summary():
    """Summary system prompt must tell the model to use ONLY the document text."""
    system_prompt = prompt_builder.get_system_prompt("summary")
    assert "summarize ONLY the document text provided" in system_prompt
    assert "Do not use outside knowledge to invent document content" in system_prompt
    assert "Do not assume the document topic" in system_prompt

    # The user prompt template must also carry the source-only directive.
    user_prompt = prompt_builder.build_prompt("summary", "Some document text.")
    assert "Do NOT use outside knowledge" in user_prompt


def test_streaming_analysis_uses_documents_text(patched_pipeline, fake_llm):
    """Streaming path also sends the requested document's text to the LLM."""
    import asyncio

    doc = FakeDocument(
        1,
        "alpha.pdf",
        "ALPHA-ONLY-CONTENT streaming summary text.",
        chunk_texts=["ALPHA-ONLY-CONTENT streaming summary text."],
    )
    patched_pipeline(doc)
    fake_llm.calls.clear()

    async def collect():
        events = []
        async for event in analysis_service.analyze_document_stream(
            document_id=doc.id,
            analysis_type="summary",
            user_id=1,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    assert fake_llm.calls, "Streaming LLM should have been called"
    messages = fake_llm.calls[-1]["messages"]
    user_prompt = [m["content"] for m in messages if m["role"] == "user"][0]
    assert "ALPHA-ONLY-CONTENT" in user_prompt
    # Streamed chunks should arrive and a done event should terminate.
    assert any('"type": "chunk"' in e for e in events)
    assert any('"type": "done"' in e for e in events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# Layout-preserving table extraction
# ---------------------------------------------------------------------------

def test_join_segments_preserves_column_alignment():
    """Separate table columns must not be glued into one token run."""
    from services.parsers.pdf_parser import _join_segments
    row = _join_segments([(40.0, "Apolipoprotein B"), (260.0, "46.00"), (330.0, "mg/dL")])
    assert "Apolipoprotein B" in row
    assert "46.00" in row
    assert "mg/dL" in row
    # The wide gap produces padding so the number does not merge with the name.
    assert "B46.00" not in row
    assert "B 46.00" not in row


def test_join_segments_close_tokens_single_space():
    from services.parsers.pdf_parser import _join_segments
    row = _join_segments([(10.0, "GLUCOSE,"), (12.0, "FASTING")])
    assert row == "GLUCOSE, FASTING"


def test_pdf_parser_layout_extraction_keeps_table_rows():
    """A real table PDF must produce aligned rows, not a flattened blob."""
    import tempfile
    import shutil
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from services.parsers.pdf_parser import PDFParser

    tmp = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp, "table.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    data = [
        ["Test Name", "Results", "Units", "Bio. Ref. Interval"],
        ["Apolipoprotein B", "46.00", "mg/dL", "46 - 174"],
        ["Glucose, Fasting", "88", "mg/dL", "70 - 100"],
    ]
    table = Table(data)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, "black")]))
    doc.build([Paragraph("Test Report", getSampleStyleSheet()["Normal"]), table])

    result = PDFParser().parse(pdf_path)
    text = result.text
    assert result.word_count > 0

    # All four header cells should be on one visual line.
    header_lines = [
        ln for ln in text.splitlines()
        if "Test Name" in ln and "Results" in ln and "Units" in ln
    ]
    assert header_lines, f"No aligned header row found in:\n{text}"

    # A data row keeps value + unit + name together (not flattened apart).
    row_lines = [ln for ln in text.splitlines() if "Apolipoprotein B" in ln]
    assert row_lines, f"No data row found in:\n{text}"
    assert any("46.00" in ln and "mg/dL" in ln for ln in row_lines)

    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Source-only rule / verified-values prompt hardening
# ---------------------------------------------------------------------------

def test_lab_report_template_contains_source_only_rule():
    template = prompt_builder.get_template("lab_report")
    # The raw template references the rule placeholder; build_prompt expands it.
    assert "{source_only_rule}" in template
    assert "VERIFIED VALUES" in template
    assert "Bio. Ref. Interval" in template

    expanded = prompt_builder.build_prompt("lab_report", "Some lab text.")
    assert "SOURCE-ONLY RULE" in expanded
    assert "could not be reliably determined from the extracted text" in expanded


def test_build_prompt_injects_source_only_rule():
    summary_prompt = prompt_builder.build_prompt("summary", "Some document text.")
    assert "SOURCE-ONLY RULE" in summary_prompt
    assert "Do not move a value from one test to another" in summary_prompt
    assert "{source_only_rule}" not in summary_prompt  # no leftover placeholder

    lab_prompt = prompt_builder.build_prompt("lab_report", "Some lab text.")
    assert "SOURCE-ONLY RULE" in lab_prompt
    assert "VERIFIED VALUES" in lab_prompt


def test_lab_report_system_prompt_follows_source_only_rule():
    system_prompt = prompt_builder.get_system_prompt("lab_report")
    assert "SOURCE-ONLY RULE" in system_prompt
    assert "never invent or infer results" in system_prompt
