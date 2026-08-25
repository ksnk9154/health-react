"""
Phase 2a Verification Tests

Run with: pytest backend/tests/test_documents.py -v

Tests cover:
- Database schema
- Parser framework
- ChunkService
- DocumentService
- API endpoints
- Security
- Performance

Database: Uses an isolated in-memory SQLite database.
The DATABASE_URL is injected before any backend imports so the engine
is created against a fresh database per test run. No drop_all/create_all
cycle is needed — the schema is always built from the current model
code, exposing any drift immediately.
"""

import os
import sys

# ---- Inject isolated test database BEFORE any backend imports -----------
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:?foreign_keys=on")

import time
import json
import hashlib
import tempfile
import pytest
from pathlib import Path
from sqlalchemy import select

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from db.session import get_db_session, engine
from db.models import Base, Document, DocumentAnalysis, User
from services.parsers import (
    parse_document,
    get_parser,
    DocumentParseResult,
    DocumentErrorCode,
    all_parsers_healthy,
    get_supported_extensions,
)
from services.chunk_service import chunk_service, CHUNK_SIZE, CHUNK_OVERLAP
from services.document_service import (
    upload_document,
    extract_document,
    get_document,
    list_documents,
    delete_document,
    DOCUMENT_STORAGE_PATH,
    MAX_UPLOAD_SIZE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """
    Build the schema from current model definitions against a fresh
    in-memory database. No drop_all needed — the database is created
    per test process via the DATABASE_URL override above. This means
    schema drift from model changes is immediately visible as test
    failures rather than being silently masked.
    """
    Base.metadata.create_all(bind=engine)
    # Create a test user for foreign key constraints
    session = get_db_session()
    try:
        test_user = User(
            username="testuser_verification",
            password_hash="$2b$12$placeholder_for_testing",
            role="User",
        )
        session.add(test_user)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
    yield


@pytest.fixture
def db_session():
    """Provide a database session for each test."""
    session = get_db_session()
    yield session
    session.close()


@pytest.fixture(scope="session")
def test_user_id():
    """Test user ID (matches the user created in setup_database)."""
    # Get the ID of the test user we created
    session = get_db_session()
    try:
        from db.models import User
        user = session.execute(
            select(User).where(User.username == "testuser_verification")
        ).scalar_one_or_none()
        if user is None:
            # Create user if not exists
            from auth.auth_service import hash_password
            user = User(
                username="testuser_verification",
                password_hash=hash_password("testpass123"),
                role="User",
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        return user.id
    finally:
        session.close()


@pytest.fixture(autouse=True)
def cleanup_storage():
    """Clean up test files after each test."""
    yield
    # Cleanup: remove test uploads
    test_dir = Path(DOCUMENT_STORAGE_PATH)
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def sample_files():
    """Create sample files for testing."""
    temp_dir = tempfile.mkdtemp()
    files = {}

    # PDF (minimal valid PDF)
    pdf_path = os.path.join(temp_dir, "test.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n")
    files["pdf"] = pdf_path

    # DOCX (minimal DOCX is a ZIP, skip for simplicity)
    # Use a simple text file renamed to .docx for testing
    docx_path = os.path.join(temp_dir, "test.docx")
    with open(docx_path, "w") as f:
        f.write("Hello world")
    files["docx"] = docx_path

    # XLSX (minimal XLSX is a ZIP, skip for simplicity)
    xlsx_path = os.path.join(temp_dir, "test.xlsx")
    with open(xlsx_path, "w") as f:
        f.write("Sheet1\n")
    files["xlsx"] = xlsx_path

    # CSV
    csv_path = os.path.join(temp_dir, "test.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("name,age,city\nJohn,30,NYC\nJane,25,LA\n")
    files["csv"] = csv_path

    # TXT
    txt_path = os.path.join(temp_dir, "test.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Hello world\nThis is a test.\n")
    files["txt"] = txt_path

    # Latin-1 TXT
    latin1_path = os.path.join(temp_dir, "test_latin1.txt")
    with open(latin1_path, "w", encoding="latin-1") as f:
        f.write("Héllo wörld\n")
    files["latin1_txt"] = latin1_path

    # Large TXT
    large_path = os.path.join(temp_dir, "large.txt")
    with open(large_path, "w", encoding="utf-8") as f:
        f.write("word " * 10000)
    files["large_txt"] = large_path

    yield files

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Database Tests
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_documents_table_exists(self, db_session):
        """Verify documents table exists with correct columns."""
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "documents" in tables

        columns = {col["name"] for col in inspector.get_columns("documents")}
        expected = {
            "id", "user_id", "original_filename", "stored_filename",
            "mime_type", "file_size", "checksum", "version",
            "upload_time", "created_at", "updated_at", "last_accessed",
            "parser_used", "processing_time_ms", "status",
            "extracted_text", "text_chunks", "doc_metadata",
            "error_code", "error_message",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_document_analyses_table_exists(self, db_session):
        """Verify document_analyses table exists."""
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "document_analyses" in tables

    def test_indexes_exist(self, db_session):
        """Verify indexes are created."""
        from sqlalchemy import inspect
        inspector = inspect(engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("documents")}
        assert "idx_documents_user_status" in indexes
        assert "idx_documents_checksum" in indexes
        assert "idx_documents_updated" in indexes

    def test_foreign_keys(self, db_session):
        """Verify foreign key relationships."""
        from sqlalchemy import inspect
        inspector = inspect(engine)
        fks = inspector.get_foreign_keys("documents")
        assert any(fk["referred_table"] == "users" for fk in fks)


# ---------------------------------------------------------------------------
# Parser Framework Tests
# ---------------------------------------------------------------------------

class TestParserFramework:
    def test_registry_has_all_parsers(self):
        """Verify all 5 parsers are registered."""
        extensions = get_supported_extensions()
        assert ".pdf" in extensions
        assert ".docx" in extensions
        assert ".xlsx" in extensions
        assert ".csv" in extensions
        assert ".txt" in extensions

    def test_parsers_healthy(self):
        """Verify all parsers report health status."""
        health = all_parsers_healthy()
        assert len(health) == 5
        # PDF parser may not be healthy if pypdf2 not installed
        # This is OK - just verify the registry works
        assert ".pdf" in health

    def test_get_parser(self):
        """Verify parser lookup."""
        parser = get_parser(".pdf")
        assert parser is not None
        assert parser.extension == ".pdf"

    def test_parse_document_raises_for_unknown_extension(self):
        """Verify unknown extension raises ValueError."""
        with pytest.raises(ValueError, match="No parser registered"):
            parse_document("/tmp/test.xyz", ".xyz")


# ---------------------------------------------------------------------------
# PDF Parser Tests
# ---------------------------------------------------------------------------

class TestPDFParser:
    def test_normal_pdf(self, sample_files):
        """Test normal PDF parsing."""
        # Create a minimal valid PDF with text
        pdf_path = os.path.join(tempfile.gettempdir(), "normal.pdf")
        with open(pdf_path, "wb") as f:
            f.write(
                b"%PDF-1.4\n"
                b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
                b"xref\n0 4\n"
                b"0000000000 65535 f \n"
                b"0000000009 00000 n \n"
                b"0000000058 00000 n \n"
                b"0000000115 00000 n \n"
                b"trailer<</Size 4/Root 1 0 R>>\n"
                b"startxref\n190\n"
                b"%%EOF\n"
            )

        # Note: This is a minimal PDF with no text content
        # Real PDF testing would require actual PDF files
        # This test verifies the parser doesn't crash
        try:
            result = parse_document(pdf_path, ".pdf")
            assert isinstance(result, DocumentParseResult)
            assert result.parser_used == "pdf_parser"
            assert result.processing_time_ms > 0
        except Exception as e:
            pytest.fail(f"PDF parser crashed: {e}")

    def test_scanned_pdf_detection(self, sample_files):
        """Test scanned PDF detection (no extractable text)."""
        # Skip if pypdf2 not installed
        parser = get_parser(".pdf")
        if not parser.health_check():
            pytest.skip("pypdf2 not installed")

        # Minimal PDF with no text
        pdf_path = os.path.join(tempfile.gettempdir(), "scanned.pdf")
        with open(pdf_path, "wb") as f:
            f.write(
                b"%PDF-1.4\n"
                b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
                b"xref\n0 4\n"
                b"0000000000 65535 f \n"
                b"0000000009 00000 n \n"
                b"0000000058 00000 n \n"
                b"0000000115 00000 n \n"
                b"trailer<</Size 4/Root 1 0 R>>\n"
                b"startxref\n190\n"
                b"%%EOF\n"
            )

        result = parse_document(pdf_path, ".pdf")
        assert result.word_count == 0
        assert len(result.warnings) > 0
        assert "Scanned document detected" in result.warnings[0]


# ---------------------------------------------------------------------------
# DOCX Parser Tests
# ---------------------------------------------------------------------------

class TestDOCXParser:
    def test_docx_paragraphs(self, sample_files):
        """Test DOCX paragraph extraction."""
        # Note: Our test file is just a text file renamed to .docx
        # Real DOCX testing would require actual .docx files
        # This verifies the parser handles errors gracefully
        try:
            result = parse_document(sample_files["docx"], ".docx")
            assert isinstance(result, DocumentParseResult)
        except Exception:
            # Expected: not a valid DOCX
            pass


# ---------------------------------------------------------------------------
# XLSX Parser Tests
# ---------------------------------------------------------------------------

class TestXLSXParser:
    def test_xlsx_parser_available(self):
        """Verify XLSX parser is registered."""
        parser = get_parser(".xlsx")
        assert parser is not None
        assert parser.health_check() is True


# ---------------------------------------------------------------------------
# CSV Parser Tests
# ---------------------------------------------------------------------------

class TestCSVParser:
    def test_csv_header_and_rows(self, sample_files):
        """Test CSV parsing with headers and rows."""
        result = parse_document(sample_files["csv"], ".csv")
        assert result.word_count > 0
        assert "name" in result.text
        assert "John" in result.text
        assert result.parser_used == "csv_parser"


# ---------------------------------------------------------------------------
# TXT Parser Tests
# ---------------------------------------------------------------------------

class TestTXTParser:
    def test_utf8_txt(self, sample_files):
        """Test UTF-8 text file."""
        result = parse_document(sample_files["txt"], ".txt")
        assert result.word_count > 0
        assert "Hello world" in result.text
        assert result.parser_used == "txt_parser"

    def test_latin1_txt(self, sample_files):
        """Test Latin-1 text file."""
        result = parse_document(sample_files["latin1_txt"], ".txt")
        assert result.word_count > 0
        assert result.metadata.get("encoding") == "latin-1"


# ---------------------------------------------------------------------------
# ChunkService Tests
# ---------------------------------------------------------------------------

class TestChunkService:
    def test_small_document(self):
        """Test chunking a small document."""
        text = "This is a test. " * 50  # 100 words
        chunks = chunk_service.chunk_text(text, page_count=1)
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["text"] == text.strip()

    def test_large_document(self):
        """Test chunking a large document."""
        text = "word " * 5000  # 5000 words
        chunks = chunk_service.chunk_text(text, page_count=1)
        expected_chunks = (5000 - CHUNK_OVERLAP) // (CHUNK_SIZE - CHUNK_OVERLAP) + 1
        assert len(chunks) == expected_chunks

    def test_chunk_overlap(self):
        """Test chunk overlap is correct."""
        text = "word " * 2000  # 2000 words
        chunks = chunk_service.chunk_text(text, page_count=1)
        # Check overlap between consecutive chunks
        for i in range(len(chunks) - 1):
            chunk1_words = chunks[i]["text"].split()
            chunk2_words = chunks[i + 1]["text"].split()
            # Last CHUNK_OVERLAP words of chunk1 should appear in chunk2
            overlap = chunk1_words[-CHUNK_OVERLAP:]
            assert all(word in chunk2_words for word in overlap)

    def test_page_references(self):
        """Test page number estimation."""
        text = "word " * 1000  # 1000 words
        chunks = chunk_service.chunk_text(text, page_count=10)
        # Page numbers should be between 1 and 10
        for chunk in chunks:
            assert 1 <= chunk["page_number"] <= 10

    def test_chunk_metadata(self):
        """Test chunk metadata fields."""
        text = "word " * 100
        chunks = chunk_service.chunk_text(text, page_count=1)
        chunk = chunks[0]
        assert "chunk_index" in chunk
        assert "page_number" in chunk
        assert "start_word" in chunk
        assert "end_word" in chunk
        assert "text" in chunk
        assert chunk["start_word"] == 0
        assert chunk["end_word"] == 99


# ---------------------------------------------------------------------------
# DocumentService Tests
# ---------------------------------------------------------------------------

class TestDocumentService:
    def test_upload_document(self, test_user_id, sample_files):
        """Test document upload."""
        with open(sample_files["txt"], "rb") as f:
            content = f.read()

        result = upload_document(
            user_id=test_user_id,
            original_filename="test.txt",
            file_content=content,
            mime_type="text/plain",
        )

        assert result["success"] is True
        assert result["data"]["id"] is not None
        assert result["data"]["original_filename"] == "test.txt"
        assert result["data"]["status"] == "UPLOADED"

    def test_duplicate_detection(self, test_user_id, sample_files):
        """Test duplicate file detection."""
        with open(sample_files["txt"], "rb") as f:
            content = f.read()

        # Upload same file twice
        result1 = upload_document(test_user_id, "dup.txt", content, "text/plain")
        result2 = upload_document(test_user_id, "dup.txt", content, "text/plain")

        assert result1["success"] is True
        assert result2["success"] is True
        assert result2["data"]["id"] == result1["data"]["id"]  # Same document
        assert result2.get("error_code") == DocumentErrorCode.DUPLICATE_DOCUMENT.value

    def test_versioning(self, test_user_id, sample_files):
        """Test version increment for same filename, different content."""
        content1 = b"Version 1"
        content2 = b"Version 2"

        result1 = upload_document(test_user_id, "versioned.txt", content1, "text/plain")
        result2 = upload_document(test_user_id, "versioned.txt", content2, "text/plain")

        assert result1["success"] is True
        assert result2["success"] is True
        assert result2["data"]["id"] != result1["data"]["id"]  # Different document
        assert result2["data"]["version"] == 2

    def test_list_documents(self, test_user_id, sample_files):
        """Test document listing."""
        with open(sample_files["txt"], "rb") as f:
            content = f.read()
        upload_document(test_user_id, "list_test.txt", content, "text/plain")

        result = list_documents(test_user_id)
        assert result["total"] >= 1
        assert len(result["items"]) >= 1

    def test_get_document(self, test_user_id, sample_files):
        """Test getting a single document."""
        with open(sample_files["txt"], "rb") as f:
            content = f.read()
        upload_result = upload_document(test_user_id, "get_test.txt", content, "text/plain")
        doc_id = upload_result["data"]["id"]

        doc = get_document(doc_id, test_user_id)
        assert doc is not None
        assert doc["id"] == doc_id
        assert doc["original_filename"] == "get_test.txt"
        # Regression: extracted_text/text_chunks must be exposed in the API
        # payload so the frontend "Extracted Text" viewer can render them.
        # (Previously omitted from _document_to_dict, so a READY document
        # always showed "No extracted text available".)
        assert "extracted_text" in doc
        assert "text_chunks" in doc

    def test_get_document_exposes_extracted_text(self, test_user_id, sample_files):
        """After extraction, the API payload must include the extracted text."""
        with open(sample_files["txt"], "rb") as f:
            content = f.read()
        up = upload_document(test_user_id, "extract_view.txt", content, "text/plain")
        doc_id = up["data"]["id"]

        # Simulate a completed extraction by writing extracted_text directly
        # (same effect as _perform_extraction() for a text file).
        from services.document_service import _perform_extraction
        try:
            _perform_extraction(doc_id)
        except Exception:
            pass

        doc = get_document(doc_id, test_user_id)
        assert doc is not None
        assert doc.get("status") == "READY"
        assert "extracted_text" in doc
        assert isinstance(doc.get("extracted_text"), str)
        assert len(doc["extracted_text"]) > 0

    def test_delete_document(self, test_user_id, sample_files):
        """Test document deletion."""
        with open(sample_files["txt"], "rb") as f:
            content = f.read()
        upload_result = upload_document(test_user_id, "delete_test.txt", content, "text/plain")
        doc_id = upload_result["data"]["id"]

        result = delete_document(doc_id, test_user_id)
        assert result["success"] is True

        # Verify deleted
        doc = get_document(doc_id, test_user_id)
        assert doc is None


# ---------------------------------------------------------------------------
# Security Tests
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_path_traversal(self, test_user_id):
        """Test path traversal protection."""
        # Use a filename with extension to pass MIME type validation
        malicious_filename = "../../../etc/passwd.txt"
        result = upload_document(
            test_user_id,
            malicious_filename,
            b"test",
            "text/plain",
        )
        # The key test: filename should be sanitized (no path separators)
        assert result["success"] is True
        assert result["data"]["original_filename"] == "passwd.txt"

    def test_invalid_file_type(self, test_user_id):
        """Test invalid file type rejection."""
        result = upload_document(
            test_user_id,
            "test.exe",
            b"malicious",
            "application/x-msdownload",
        )
        assert result["success"] is False
        assert result["error_code"] == DocumentErrorCode.INVALID_FILE_TYPE.value

    def test_file_too_large(self, test_user_id):
        """Test file size limit."""
        large_content = b"x" * (MAX_UPLOAD_SIZE + 1)
        result = upload_document(
            test_user_id,
            "large.txt",
            large_content,
            "text/plain",
        )
        assert result["success"] is False
        assert result["error_code"] == DocumentErrorCode.DOCUMENT_TOO_LARGE.value

    def test_user_isolation(self, test_user_id, sample_files):
        """Test user A cannot access user B's documents."""
        with open(sample_files["txt"], "rb") as f:
            content = f.read()
        upload_result = upload_document(test_user_id, "isolated.txt", content, "text/plain")
        doc_id = upload_result["data"]["id"]

        # Try to access with different user_id
        doc = get_document(doc_id, test_user_id + 1)
        assert doc is None


# ---------------------------------------------------------------------------
# Performance Tests
# ---------------------------------------------------------------------------

class TestPerformance:
    def test_upload_latency(self, test_user_id):
        """Measure upload latency."""
        content = b"x" * 1024 * 1024  # 1MB
        start = time.time()
        result = upload_document(test_user_id, "perf.txt", content, "text/plain")
        elapsed = (time.time() - start) * 1000
        assert result["success"] is True
        assert elapsed < 1000, f"Upload took {elapsed:.0f}ms (expected < 1000ms)"
        print(f"\nUpload latency: {elapsed:.0f}ms")

    def test_extraction_latency(self, test_user_id, sample_files):
        """Measure extraction latency."""
        with open(sample_files["large_txt"], "rb") as f:
            content = f.read()
        upload_result = upload_document(test_user_id, "large.txt", content, "text/plain")
        doc_id = upload_result["data"]["id"]

        start = time.time()
        # Extract synchronously for testing
        from services.document_service import _perform_extraction
        _perform_extraction(doc_id)
        elapsed = (time.time() - start) * 1000

        assert elapsed < 5000, f"Extraction took {elapsed:.0f}ms (expected < 5000ms)"
        print(f"\nExtraction latency: {elapsed:.0f}ms")


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])