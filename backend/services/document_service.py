"""DocumentService — Business logic for document management."""

import os
import re
import json
import time
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from db.session import get_db_session
from db.models import Document, DocumentAnalysis
from services.parsers import parse_document, get_parser, DocumentParseResult, DocumentErrorCode
from services.chunk_service import chunk_service
from services.task_service import task_service
from services.health_observation_service import store_document_observations

logger = logging.getLogger(__name__)

# Configuration
DOCUMENT_STORAGE_PATH = os.environ.get("DOCUMENT_STORAGE_PATH", "storage/uploads")
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE_MB", 20)) * 1024 * 1024
MAX_PAGES = int(os.environ.get("MAX_DOCUMENT_PAGES", 500))
MAX_WORDS = int(os.environ.get("MAX_DOCUMENT_WORDS", 100000))

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string (no microseconds, fits VARCHAR(30))."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize_filename(filename: str) -> str:
    """Strip path separators and dangerous characters from filename."""
    # Remove path separators
    filename = os.path.basename(filename)
    # Remove any remaining path-like characters
    filename = re.sub(r'[\\/:*?"<>|]', '', filename)
    return filename.strip() or "unnamed"


def _compute_checksum(file_content: bytes) -> str:
    """Compute SHA-256 checksum of file content."""
    return hashlib.sha256(file_content).hexdigest()


def _get_user_storage_path(user_id: int) -> str:
    """Get the storage directory for a user, creating it if needed."""
    user_dir = os.path.join(DOCUMENT_STORAGE_PATH, str(user_id))
    originals_dir = os.path.join(user_dir, "originals")
    extracted_dir = os.path.join(user_dir, "extracted")
    thumbnails_dir = os.path.join(user_dir, "thumbnails")

    for directory in [originals_dir, extracted_dir, thumbnails_dir]:
        os.makedirs(directory, exist_ok=True)

    return user_dir


def _get_next_version(session: Session, user_id: int, original_filename: str) -> int:
    """Get the next version number for a document with the same filename."""
    latest = session.execute(
        select(Document)
        .where(Document.user_id == user_id, Document.original_filename == original_filename)
        .order_by(Document.version.desc())
    ).scalar_one_or_none()

    return (latest.version + 1) if latest else 1


def _check_duplicate(session: Session, user_id: int, checksum: str, original_filename: str) -> Optional[Document]:
    """Check for duplicate documents. Returns existing document if exact duplicate found, None otherwise."""
    # Exact duplicate: same user, same filename, same checksum
    existing = session.execute(
        select(Document)
        .where(
            Document.user_id == user_id,
            Document.original_filename == original_filename,
            Document.checksum == checksum,
        )
    ).scalar_one_or_none()

    return existing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_document(
    user_id: int,
    original_filename: str,
    file_content: bytes,
    mime_type: str,
) -> Dict[str, Any]:
    """
    Upload a document.

    Args:
        user_id: User ID from JWT
        original_filename: Original filename from user
        file_content: Raw file bytes
        mime_type: MIME type from upload

    Returns:
        Dict with document data or error
    """
    session = get_db_session()
    try:
        # 1. Validate extension
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return {
                "success": False,
                "message": f"File type '{ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS.keys())}",
                "error_code": DocumentErrorCode.INVALID_FILE_TYPE.value,
                "data": None,
            }

        # 2. Validate MIME type
        if mime_type != ALLOWED_EXTENSIONS[ext]:
            return {
                "success": False,
                "message": f"MIME type mismatch. Expected '{ALLOWED_EXTENSIONS[ext]}', got '{mime_type}'",
                "error_code": DocumentErrorCode.INVALID_FILE_TYPE.value,
                "data": None,
            }

        # 3. Validate file size
        if len(file_content) > MAX_UPLOAD_SIZE:
            return {
                "success": False,
                "message": f"File too large. Maximum size: {MAX_UPLOAD_SIZE // (1024*1024)}MB",
                "error_code": DocumentErrorCode.DOCUMENT_TOO_LARGE.value,
                "data": None,
            }

        # 4. Compute checksum
        checksum = _compute_checksum(file_content)

        # 5. Sanitize filename
        safe_filename = _sanitize_filename(original_filename)

        # 6. Check for duplicates
        existing = _check_duplicate(session, user_id, checksum, safe_filename)
        if existing:
            logger.info("Duplicate document detected: user=%d, filename=%s, checksum=%s",
                       user_id, safe_filename, checksum)
            return {
                "success": True,
                "message": "Document already exists",
                "error_code": DocumentErrorCode.DUPLICATE_DOCUMENT.value,
                "data": _document_to_dict(existing),
            }

        # 7. Determine version
        version = _get_next_version(session, user_id, safe_filename)

        # 8. Generate storage filename
        stored_filename = f"{uuid.uuid4()}{ext}"

        # 9. Save file
        user_storage = _get_user_storage_path(user_id)
        originals_dir = os.path.join(user_storage, "originals")
        filepath = os.path.join(originals_dir, stored_filename)

        try:
            with open(filepath, "wb") as f:
                f.write(file_content)
        except Exception as e:
            logger.error("Failed to save file: %s", e)
            return {
                "success": False,
                "message": f"Failed to save file: {e}",
                "error_code": DocumentErrorCode.UPLOAD_FAILED.value,
                "data": None,
            }

        # 10. Create DB record
        now = _now_iso()
        document = Document(
            user_id=user_id,
            original_filename=safe_filename,
            stored_filename=stored_filename,
            mime_type=mime_type,
            file_size=len(file_content),
            checksum=checksum,
            version=version,
            upload_time=now,
            created_at=now,
            updated_at=now,
            status="UPLOADED",
        )

        session.add(document)
        session.commit()
        session.refresh(document)

        logger.info(
            "Document uploaded: id=%d, user=%d, filename=%s, size=%d, checksum=%s",
            document.id, user_id, safe_filename, len(file_content), checksum,
        )

                # Notify the user a document was uploaded (best-effort side-effect).
        try:
            from services.notification_service import create_notification
            create_notification(
                user_id,
                title="New health document uploaded",
                message=safe_filename,
                type="document",
                data={"document_id": document.id, "checksum": checksum},
                dedupe_key=f"upload:{user_id}:{checksum}",
            )
        except Exception:
            logger.exception("Failed to create upload notification for document %d", document.id)

        return {
            "success": True,
            "message": "Document uploaded successfully",
            "data": _document_to_dict(document),
        }

    except Exception as e:
        session.rollback()
        logger.error("Upload failed: %s", e)
        return {
            "success": False,
            "message": f"Upload failed: {e}",
            "error_code": DocumentErrorCode.UPLOAD_FAILED.value,
            "data": None,
        }
    finally:
        session.close()


def extract_document(document_id: int, user_id: int, background_tasks) -> Dict[str, Any]:
    """
    Extract text from a document.

    Args:
        document_id: Document ID
        user_id: User ID (for authorization)
        background_tasks: FastAPI BackgroundTasks instance

    Returns:
        Dict with extraction result
    """
    session = get_db_session()
    try:
        # 1. Get document
        document = session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        ).scalar_one_or_none()

        if not document:
            return {
                "success": False,
                "message": "Document not found",
                "error_code": DocumentErrorCode.DOCUMENT_NOT_FOUND.value,
                "data": None,
            }

        if document.status == "EXTRACTING":
            return {
                "success": False,
                "message": "Extraction already in progress",
                "error_code": DocumentErrorCode.EXTRACTION_FAILED.value,
                "data": None,
            }

        if document.status == "READY":
            meta = {}
            if document.doc_metadata:
                try:
                    meta = json.loads(document.doc_metadata)
                except json.JSONDecodeError:
                    pass

            # Backfill deterministic observations for documents that were
            # extracted before observation extraction was introduced to the
            # pipeline.  Extraction is idempotent (the stale observations are
            # replaced), non-fatal, and only touches READY documents that have
            # text.  This ensures the "Analyze My Health Data" flow can see
            # document-derived observations even on legacy uploads.
            if document.extracted_text:
                try:
                    observation_count = store_document_observations(session, document)
                    meta["health_observation_count"] = observation_count
                    document.doc_metadata = json.dumps(meta)
                    session.commit()
                except Exception:
                    session.rollback()
                    logger.exception(
                        "Observation backfill failed for ready document %d",
                        document.id,
                    )

            return {
                "success": True,
                "message": "Document already extracted",
                "data": {
                    "id": document.id,
                    "status": document.status,
                    "word_count": meta.get("word_count"),
                    "observation_count": meta.get("health_observation_count"),
                },
            }
        # 2. Update status to EXTRACTING
        document.status = "EXTRACTING"
        document.updated_at = _now_iso()
        session.commit()

        # 3. Submit background task
        def _extract_task(doc_id: int):
            _perform_extraction(doc_id)

        task_service.submit(background_tasks, _extract_task, document_id)

        logger.info("Extraction queued: document_id=%d", document_id)

        return {
            "success": True,
            "message": "Extraction started",
            "data": {
                "id": document.id,
                "status": "EXTRACTING",
            },
        }

    except Exception as e:
        session.rollback()
        logger.error("Extraction failed: %s", e)
        return {
            "success": False,
            "message": f"Extraction failed: {e}",
            "error_code": DocumentErrorCode.EXTRACTION_FAILED.value,
            "data": None,
        }
    finally:
        session.close()


def _perform_extraction(document_id: int):
    """Perform actual extraction (runs in background)."""
    session = get_db_session()
    try:
        document = session.execute(
            select(Document).where(Document.id == document_id)
        ).scalar_one_or_none()

        if not document:
            logger.error("Document not found for extraction: %d", document_id)
            return

        # 1. Get file path
        user_storage = os.path.join(DOCUMENT_STORAGE_PATH, str(document.user_id))
        filepath = os.path.join(user_storage, "originals", document.stored_filename)

        if not os.path.exists(filepath):
            document.status = "FAILED"
            document.error_code = DocumentErrorCode.EXTRACTION_FAILED.value
            document.error_message = "File not found on disk"
            document.updated_at = _now_iso()
            session.commit()
            return

        # 2. Parse document
        ext = os.path.splitext(document.stored_filename)[1].lower()
        result: DocumentParseResult = parse_document(filepath, ext)

        # 3. Check for warnings (e.g., scanned PDF)
        if result.warnings:
            document.error_code = DocumentErrorCode.PARSER_FAILED.value
            document.error_message = "; ".join(result.warnings)

        # 4. Chunk text if extraction succeeded
        text_chunks = []
        if result.text:
            text_chunks = chunk_service.chunk_text(result.text, result.page_count)

        # 5. Save extracted text to file
        extracted_filename = f"{os.path.splitext(document.stored_filename)[0]}.txt"
        extracted_dir = os.path.join(user_storage, "extracted")
        extracted_path = os.path.join(extracted_dir, extracted_filename)
        with open(extracted_path, "w", encoding="utf-8") as f:
            f.write(result.text)

        # 6. Update document
        document.extracted_text = result.text
        document.text_chunks = json.dumps(text_chunks)
        document.doc_metadata = json.dumps(result.metadata)
        document.parser_used = result.parser_used
        document.processing_time_ms = result.processing_time_ms
        document.status = "READY" if result.text else "FAILED"
        document.updated_at = _now_iso()

        if result.text:
            # Store word_count and page_count in metadata for easy access
            meta = json.loads(document.doc_metadata) if document.doc_metadata else {}
            meta["word_count"] = result.word_count
            meta["page_count"] = result.page_count
            document.doc_metadata = json.dumps(meta)

            # Observation extraction is deterministic and non-fatal: the document
            # remains usable even when no verified measurement can be found.
            try:
                observation_count = store_document_observations(session, document)
                meta["health_observation_count"] = observation_count
                document.doc_metadata = json.dumps(meta)
            except Exception:
                logger.exception("Health observation extraction failed for document %d", document_id)

        session.commit()

        # ---- Event-driven notifications (best-effort, never break extraction) ----
        try:
            from services.notification_service import create_notification
            from db.models import HealthObservation

            create_notification(
                document.user_id,
                title="Document extracted",
                message=document.original_filename,
                type="document",
                data={"document_id": document.id},
            )

            # High / abnormal lab values flagged by the source report.
            abnormal = session.execute(
                select(HealthObservation).where(
                    HealthObservation.document_id == document.id,
                    HealthObservation.status.in_(("HIGH", "LOW", "ABNORMAL")),
                )
            ).scalars().all()
            for obs in abnormal:
                value = obs.value_text if obs.value_text is not None else obs.value_numeric
                create_notification(
                    document.user_id,
                    title=f"Health alert: {obs.name} is {obs.status.lower()}",
                    message=f"{obs.name}: {value} {obs.unit or ''}".strip(),
                    type="alert",
                    data={
                        "document_id": document.id,
                        "observation_id": obs.id,
                        "name": obs.name,
                        "status": obs.status,
                    },
                    dedupe_key=f"alert:{document.user_id}:{document.id}:{obs.name}",
                )
        except Exception:
            logger.exception("Failed to create extraction notifications for document %d", document.id)

        logger.info(
            "Extraction completed: document_id=%d, words=%d, chunks=%d, time=%.0fms",
            document_id, result.word_count, len(text_chunks), result.processing_time_ms,
        )

    except Exception as e:
        logger.error("Extraction failed for document %d: %s", document_id, e)
        try:
            document.status = "FAILED"
            document.error_code = DocumentErrorCode.EXTRACTION_FAILED.value
            document.error_message = str(e)
            document.updated_at = _now_iso()
            session.commit()
        except Exception:
            session.rollback()
    finally:
        session.close()


def get_document(document_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Get a single document by ID."""
    session = get_db_session()
    try:
        document = session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        ).scalar_one_or_none()

        if not document:
            return None

        # Update last_accessed
        document.last_accessed = _now_iso()
        session.commit()

        return _document_to_dict(document)
    finally:
        session.close()


def list_documents(
    user_id: int,
    search: str = "",
    doc_type: str = "",
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """
    List user's documents with pagination.

    Args:
        user_id: User ID
        search: Search in filename
        doc_type: Filter by MIME type (e.g., 'application/pdf')
        page: Page number (1-indexed)
        per_page: Items per page

    Returns:
        Dict with items, total, page, per_page
    """
    session = get_db_session()
    try:
        query = select(Document).where(Document.user_id == user_id)

        # Search
        if search:
            like = f"%{search}%"
            query = query.where(Document.original_filename.ilike(like))

        # Filter by type
        if doc_type:
            query = query.where(Document.mime_type == doc_type)

        # Count total
        from sqlalchemy import func
        count_query = select(func.count()).select_from(query.subquery())
        total = session.execute(count_query).scalar_one()

        # Paginate
        offset = (page - 1) * per_page
        query = query.order_by(desc(Document.upload_time)).offset(offset).limit(per_page)

        documents = session.execute(query).scalars().all()

        items = [_document_to_dict(doc) for doc in documents]

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    finally:
        session.close()


def delete_document(document_id: int, user_id: int) -> Dict[str, Any]:
    """
    Delete a document and its files.

    Args:
        document_id: Document ID
        user_id: User ID (for authorization)

    Returns:
        Dict with success status
    """
    session = get_db_session()
    try:
        document = session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        ).scalar_one_or_none()

        if not document:
            return {
                "success": False,
                "message": "Document not found",
                "error_code": DocumentErrorCode.DOCUMENT_NOT_FOUND.value,
            }

        # Capture details for the "document deleted" notification before removal.
        doc_filename = document.original_filename
        doc_id = document.id
        doc_user_id = document.user_id

        # 1. Delete files
        user_storage = os.path.join(DOCUMENT_STORAGE_PATH, str(user_id))
        originals_dir = os.path.join(user_storage, "originals")
        extracted_dir = os.path.join(user_storage, "extracted")

        # Delete original
        original_path = os.path.join(originals_dir, document.stored_filename)
        if os.path.exists(original_path):
            os.remove(original_path)

        # Delete extracted text
        extracted_filename = f"{os.path.splitext(document.stored_filename)[0]}.txt"
        extracted_path = os.path.join(extracted_dir, extracted_filename)
        if os.path.exists(extracted_path):
            os.remove(extracted_path)

        # 2. Delete DB record (cascades to analyses)
        session.delete(document)
        session.commit()

        logger.info("Document deleted: id=%d, user=%d", document_id, user_id)

        try:
            from services.notification_service import create_notification
            create_notification(
                doc_user_id,
                title="Document deleted",
                message=doc_filename,
                type="document",
                data={"document_id": doc_id},
                dedupe_key=f"delete:{doc_user_id}:{doc_id}",
            )
        except Exception:
            logger.exception("Failed to create delete notification for document %d", doc_id)

        return {
            "success": True,
            "message": "Document deleted successfully",
        }

    except Exception as e:
        session.rollback()
        logger.error("Delete failed: %s", e)
        return {
            "success": False,
            "message": f"Delete failed: {e}",
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _document_to_dict(document: Document) -> Dict[str, Any]:
    """Convert Document model to dict for API response."""
    doc_meta = {}
    if document.doc_metadata:
        try:
            doc_meta = json.loads(document.doc_metadata)
        except json.JSONDecodeError:
            pass

    return {
        "id": document.id,
        "original_filename": document.original_filename,
        "stored_filename": document.stored_filename,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "checksum": document.checksum,
        "version": document.version,
        "upload_time": document.upload_time,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "last_accessed": document.last_accessed,
        "parser_used": document.parser_used,
        "processing_time_ms": document.processing_time_ms,
        "status": document.status,
        "word_count": doc_meta.get("word_count"),
        "page_count": doc_meta.get("page_count"),
        "metadata": doc_meta,
        "extracted_text": document.extracted_text,
        "text_chunks": document.text_chunks,
        "error_code": document.error_code,
        "error_message": document.error_message,
    }
