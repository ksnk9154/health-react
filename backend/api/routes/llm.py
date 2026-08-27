import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict

from api.deps import get_current_user
from services.analytics import get_user_scope_user_ids
from services.llm_service import LLMService
from services.records import list_records
from services.health_observation_service import list_observations
from services.notification_service import create_notification

logger = logging.getLogger(__name__)
router = APIRouter()

# History sanitation limits (defensive: keep prompt size bounded)
_MAX_HISTORY_ENTRIES = 20
_MAX_HISTORY_CHARS = 4000


def _validate_history(history) -> List[Dict[str, str]]:
    """Sanitize chat history sent by the client.

    Never raises — invalid entries are dropped so a malformed history can
    never turn /llm/chat into a 500. Each kept entry becomes
    {"role": "user"|"assistant", "content": "<stripped, length-capped>"}.
    """
    if not history:
        return []
    if not isinstance(history, list):
        return []

    validated: List[Dict[str, str]] = []
    for entry in history[:_MAX_HISTORY_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        validated.append({"role": role, "content": content[:_MAX_HISTORY_CHARS]})
    return validated


def _get_service() -> LLMService:
    return LLMService()



class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: Optional[List[dict]] = None
    language: Optional[str] = Field(default=None, max_length=10)


class AnalyzeRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=20)
    language: Optional[str] = Field(default=None, max_length=10)


class SuggestionsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=20)
    language: Optional[str] = Field(default=None, max_length=10)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    model: str
    mode: Optional[str] = None  # "local" | "cloud" | "unavailable"
    model_available: Optional[bool] = None
    available_models: Optional[List[str]] = None
    detail: Optional[str] = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    reply: str
    disclaimer: str


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    analysis: str
    disclaimer: str


class SuggestionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    suggestions: str
    disclaimer: str


@router.get("/health", response_model=HealthResponse, summary="Check local Ollama availability")
def health_check(current_user=Depends(get_current_user)):
    try:
        return HealthResponse(**_get_service().check_health())
    except Exception as exc:
        logger.exception("LLM health check failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM service unavailable") from exc


@router.post("/chat", response_model=ChatResponse, summary="Chat with the local health assistant")
def chat(req: ChatRequest, current_user=Depends(get_current_user)):
    try:
        validated_history = _validate_history(req.history)
        message = req.message.strip()
        if not message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

        health_context = _build_health_context(current_user, limit=10)
        result = _get_service().chat(
            message=message,
            history=validated_history,
            health_context=health_context,
            preferred_language=req.language,
        )
        return ChatResponse(**result)
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.exception("LLM chat failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("LLM chat failed unexpectedly")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="LLM request failed") from exc


@router.post("/analyze", response_model=AnalysisResponse, summary="Analyze recent health data")
def analyze(req: AnalyzeRequest, current_user=Depends(get_current_user)):
    try:
        health_context = _build_health_context(current_user, limit=req.limit)
        result = _get_service().analyze(
            health_context=health_context,
            preferred_language=req.language,
        )
        try:
            create_notification(
                current_user["id"],
                title="Health report generated",
                message="Your health analysis is ready",
                type="analysis",
                dedupe_key=f"analyze:{current_user['id']}",
            )
        except Exception:
            logger.exception("Failed to create analysis notification for user=%s", current_user.get("id"))
        return AnalysisResponse(**result)
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.exception("LLM analysis failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("LLM analysis failed unexpectedly")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="LLM request failed") from exc


@router.post("/suggestions", response_model=SuggestionsResponse, summary="Generate wellness suggestions")
def suggestions(req: SuggestionsRequest, current_user=Depends(get_current_user)):
    try:
        health_context = _build_health_context(current_user, limit=req.limit)
        result = _get_service().suggestions(
            health_context=health_context,
            preferred_language=req.language,
        )
        return SuggestionsResponse(**result)
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.exception("LLM suggestions failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("LLM suggestions failed unexpectedly")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="LLM request failed") from exc


def _build_health_context(current_user: dict, limit: int = 10) -> str:
    user_ids = get_user_scope_user_ids(current_user)
    rows = list_records(user_ids, search="", sort="record_date desc", filters={})
    observations = list_observations(user_ids)[: max(1, min(limit, 20))]

    # Log how many records/observations reach the LLM (user id only, no PHI) so
    # the pipeline is diagnosable in production.
    logger.info(
        "Building LLM health context for user=%s: %d health records, %d verified observations",
        current_user.get("id"), len(rows), len(observations),
    )

    # Determine whether the user has ANY uploaded documents, so "no health data"
    # is not silently conflated with "the report did not convert".
    doc_count = _count_user_documents(user_ids)
    logger.info("LLM context document count for user=%s: %d", current_user.get("id"), doc_count)

    if not rows and not observations:
        if doc_count > 0:
            return (
                f"You have {doc_count} uploaded document(s), but no verified health "
                "observations could be extracted from them yet. The report may not "
                "have been successfully converted into structured measurements, or it "
                "contained no recognizable lab values. Re-run extraction (Re-extract) "
                "on the document to retry."
            )
        return (
            "No health records or verified document observations are available for "
            "this user. Upload a health report or add a health record first."
        )

    recent_rows = rows[: max(1, min(limit, 20))]
    lines: List[str] = []
    for row in recent_rows:
        record_date = str(row.get("record_date", "unknown"))
        weight = row.get("weight_kg")
        bmi = row.get("bmi")
        calories = row.get("calories")
        water = row.get("water_liters")
        sleep = row.get("sleep_hours")
        food = str(row.get("food") or "").strip()
        exercise = str(row.get("exercise") or "").strip()

        parts = [f"Date: {record_date}"]
        if weight is not None:
            parts.append(f"Weight: {weight} kg")
        if bmi is not None:
            parts.append(f"BMI: {bmi}")
        if calories is not None:
            parts.append(f"Calories: {calories}")
        if water is not None:
            parts.append(f"Water: {water} L")
        if sleep is not None:
            parts.append(f"Sleep: {sleep} h")
        if food:
            parts.append(f"Food: {food}")
        if exercise:
            parts.append(f"Exercise: {exercise}")

        lines.append(" | ".join(parts))

    if observations:
        lines.append("Recent verified document observations:")
        for observation in observations:
            _append_observation_line(lines, observation)

    return "\n".join(lines)


def _append_observation_line(lines: List[str], observation: dict) -> None:
    """Append a single verified observation with source provenance to the context.

    Never invents a source: falls back to the stored document id from the DB row.
    Only emits fields the extractor actually populated (no hallucinated ranges).
    """
    value = observation.get("value_text") or observation.get("value_numeric")
    unit = observation.get("unit") or ""
    reference = observation.get("reference_text") or (
        f"{observation.get('reference_low')} - {observation.get('reference_high')}"
        if observation.get("reference_low") is not None else ""
    )
    doc_name = observation.get("document_name")
    source = doc_name or f"document_id={observation['document_id']}"
    if observation.get("source_page"):
        source += f", page {observation['source_page']}"
    status = observation.get("status")
    status_part = f" | Reported status: {status}" if status and status != "UNKNOWN" else ""
    ref_part = f" | Reference: {reference}" if reference else ""
    lines.append(
        f"{observation['name']}: {value} {unit}"
        f" | Source: {source}"
        f" | Confidence: {observation['confidence']}"
        f"{ref_part}{status_part}"
    )


def _count_user_documents(user_ids) -> int:
    """Count documents owned by the scoped user ids (diagnostics only)."""
    if not user_ids:
        return 0
    from db.models import Document
    from db.session import get_db_session
    from sqlalchemy import func, select

    _s = get_db_session()
    try:
        return (
            _s.execute(
                select(func.count()).select_from(Document).where(Document.user_id.in_(user_ids))
            ).scalar()
            or 0
        )
    except Exception:
        logger.debug("Could not count documents for user scope %r", user_ids, exc_info=True)
        return 0
    finally:
        _s.close()