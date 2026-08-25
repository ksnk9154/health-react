"""AnalysisService - Orchestrate document analysis pipeline."""

import os
import json
import time
import logging
import hashlib
from typing import Optional, AsyncGenerator
from datetime import datetime, timezone

from db.session import get_db_session
from db.models import Document, DocumentAnalysis
from services.llm_service import llm_service
from services.prompt_builder import prompt_builder
from services.context_selector import context_selector
from services.citation_generator import citation_generator
from services.cache_manager import cache_manager
from services.prompt_sanitizer import prompt_sanitizer
from services.output_filter import output_filter

logger = logging.getLogger(__name__)

# Configuration
# Best available now: llama3.1:8b
# Recommended upgrade: qwen2.5:7b
# Best multilingual choice: qwen3:8b (if hardware can run it)
DEFAULT_LLM_MODEL = os.environ.get("DEFAULT_LLM_MODEL", "llama3.1:8b")
MAX_RESPONSE_TOKENS = int(os.environ.get("ANALYSIS_MAX_RESPONSE_TOKENS", 1000))


class AnalysisService:
    """Orchestrate document analysis pipeline."""

    def __init__(self):
        self.llm = llm_service
        self.prompt_builder = prompt_builder
        self.context_selector = context_selector
        self.citation_generator = citation_generator
        self.cache = cache_manager
        self.default_model = DEFAULT_LLM_MODEL

    def _log_llm_context(
        self,
        document,
        chunks: list,
        selected_chunks: list,
        final_prompt: str,
        model: str,
        analysis_type: str,
    ) -> None:
        """Debug-log exactly what will be sent to the LLM (no secrets logged).

        Shows document id/filename, extracted word count, chunk counts,
        selected chunk indexes + page numbers, a short snippet of each selected
        chunk, the final prompt length, and the model. Used to verify that the
        LLM receives the correct document text.
        """
        extracted = document.extracted_text or ""
        logger.info(
            "LLM context: document_id=%s filename=%s analysis_type=%s "
            "extracted_words=%d total_chunks=%d selected_chunks=%d "
            "prompt_chars=%d model=%s",
            getattr(document, "id", "?"),
            getattr(document, "original_filename", "?"),
            analysis_type,
            len(extracted.split()),
            len(chunks),
            len(selected_chunks),
            len(final_prompt),
            model,
        )
        if selected_chunks:
            logger.info(
                "LLM context: selected chunk indexes=%s page_numbers=%s",
                [c.get("chunk_index") for c in selected_chunks],
                [c.get("page_number") for c in selected_chunks],
            )
            for c in selected_chunks:
                snippet = (c.get("text") or "")[:300].replace("\n", " ")
                logger.info(
                    "LLM context chunk %s (page %s): %s",
                    c.get("chunk_index"),
                    c.get("page_number"),
                    snippet,
                )

    async def analyze_document(
        self,
        document_id: int,
        analysis_type: str,
        user_id: int,
        question: Optional[str] = None,
        force_regenerate: bool = False,
        preferred_language: Optional[str] = None,
    ) -> dict:
        """
        Analyze document and generate analysis.

        Prompt injection hardening layers:
        1. Sanitize user question — strip control chars, detect injection patterns
        2. Boundary-mark all user content — prevent prompt boundary escape
        3. Context isolation notice — instruct LLM to treat content as data
        4. System prompt defense — instructions to never follow user commands
        5. Output filter — detect system prompt leaks, enforce disclaimers, flag PII

        Args:
            document_id: Document ID
            analysis_type: Type of analysis (summary, explanation, qa, lab_report, prescription)
            user_id: User ID (for authorization)
            question: User question (for QA)
            force_regenerate: Force regeneration, bypass cache
            preferred_language: User's UI language code (e.g., 'en', 'te', 'de').
                If set, the language is mandatory for the LLM response.

        Returns:
            Analysis result dict

        Raises:
            ValueError: If document not found, injection detected, or invalid parameters
            RuntimeError: If LLM generation fails
        """
        session = get_db_session()
        try:
            # 1. Verify document exists and user has access
            document = session.execute(
                select(Document).where(Document.id == document_id, Document.user_id == user_id)
            ).scalar_one_or_none()

            if not document:
                raise ValueError("Document not found")

            if document.status != "READY":
                raise ValueError(f"Document is not ready for analysis (status: {document.status})")

            # 2. Parse chunks
            chunks = []
            if document.text_chunks:
                try:
                    chunks = json.loads(document.text_chunks)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse chunks for document {document_id}")
                    chunks = []

            if not chunks:
                raise ValueError("Document has no extracted text chunks")

            # 3. Sanitize user question — prompt injection defense layer 1
            sanitized_question = None
            if question:
                sanitized_question = prompt_sanitizer.sanitize_question(question)
                # Check injection safety
                is_safe, detected_pattern = prompt_sanitizer.is_question_safe(question)
                if not is_safe:
                    logger.warning(
                        "Prompt injection blocked in question for document %d: %s",
                        document_id, detected_pattern
                    )
                    raise ValueError(
                        f"Question contains potentially unsafe content and was blocked. "
                        f"Detected: {detected_pattern}"
                    )

            # 4. Build prompt (sanitizer integration happens inside prompt_builder)
            prompt = self.prompt_builder.build_prompt(
                analysis_type=analysis_type,
                document_text=prompt_sanitizer.sanitize_text(
                    document.extracted_text or ""
                ),
                chunks=chunks,
                question=sanitized_question,
            )

            # 5. Generate prompt hash for cache key
            prompt_hash = self.cache._hash_prompt(prompt)

            # 6. Check cache (unless force regenerate)
            if not force_regenerate:
                cached = self.cache.get(document_id, analysis_type, prompt_hash, self.default_model)
                if cached:
                    logger.info(f"Returning cached analysis: document={document_id}, type={analysis_type}")
                    return cached

            # 7. Select relevant chunks
            selected_chunks = self.context_selector.select_chunks(
                analysis_type=analysis_type,
                chunks=chunks,
                max_tokens=4000,
                question=sanitized_question,
            )

            # 8. Build final prompt with selected chunks
            final_prompt = self.prompt_builder.build_prompt(
                analysis_type=analysis_type,
                document_text=prompt_sanitizer.sanitize_text(
                    document.extracted_text or ""
                ),
                chunks=selected_chunks,
                question=sanitized_question,
            )

            # 9. Get system prompt (includes injection defense + mandatory language)
            system_prompt = self.prompt_builder.get_system_prompt(
                analysis_type,
                preferred_language=preferred_language or "",
            )

            # 10. Log the exact context that will be sent to the LLM
            self._log_llm_context(
                document, chunks, selected_chunks, final_prompt,
                self.default_model, analysis_type,
            )

            # 10. Call LLM
            logger.info(f"Generating analysis: document={document_id}, type={analysis_type}, model={self.default_model}")
            start_time = time.time()

            try:
                response = await self.llm.chat_async(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": final_prompt},
                    ],
                    model=self.default_model,
                    stream=False,
                )
            except Exception as e:
                logger.error(f"LLM generation failed: {e}")
                raise RuntimeError(f"LLM generation failed: {e}")

            latency = time.time() - start_time
            logger.info(f"Analysis generated in {latency:.2f}s")

            # 11. Generate citations
            citations = self.citation_generator.generate_citations(selected_chunks, response)

            # 12. Filter LLM output — prompt injection defense layer 5
            filtered = output_filter.filter_response(
                response=response,
                analysis_type=analysis_type,
                source_text=document.extracted_text or "",
            )

            safe_response = filtered["content"]

            if filtered["warnings"]:
                for warning in filtered["warnings"]:
                    logger.warning("Output filter warning for analysis %d: %s", document_id, warning)

            if filtered["system_prompt_leaked"]:
                logger.error(
                    "System prompt leak detected and redacted in analysis for document %d",
                    document_id
                )

            # 13. Save to database
            analysis = DocumentAnalysis(
                document_id=document_id,
                type=analysis_type.upper(),
                content=safe_response,
                llm_model=self.default_model,
                prompt_hash=prompt_hash,
                citations=json.dumps(citations),
                generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                user_id=user_id,
            )
            session.add(analysis)
            session.commit()
            session.refresh(analysis)

            # 14. Cache result
            result = {
                "id": analysis.id,
                "type": analysis.type,
                "content": analysis.content,
                "citations": citations,
                "llm_model": analysis.llm_model,
                "generated_at": analysis.generated_at,
                "cached": False,
                "latency": latency,
                "warnings": filtered["warnings"],
                "system_prompt_leaked": filtered["system_prompt_leaked"],
                "disclaimer_added": filtered["disclaimer_added"],
            }
            self.cache.set(document_id, analysis_type, prompt_hash, self.default_model, result)

            logger.info(
                "Analysis saved: id=%d, document=%d, type=%s, warnings=%d, leaked=%s, disclaimer=%s",
                analysis.id, document_id, analysis_type,
                len(filtered["warnings"]),
                filtered["system_prompt_leaked"],
                filtered["disclaimer_added"],
            )

            return result

        except ValueError:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Analysis failed: {e}")
            raise RuntimeError(f"Analysis failed: {e}")
        finally:
            session.close()

    # ------------------------------------------------------------------
    # SSE Streaming
    # ------------------------------------------------------------------

    def _sse_chunk(self, content: str) -> str:
        """Format a text chunk as an SSE event."""
        return f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"

    def _sse_citations(self, citations: list) -> str:
        """Format citations as an SSE event."""
        return f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"

    def _sse_done(self, analysis_id: int) -> str:
        """Format a done event as an SSE event."""
        return f"data: {json.dumps({'type': 'done', 'analysis_id': analysis_id})}\n\n"

    def _sse_error(self, message: str) -> str:
        """Format an error event as an SSE event."""
        return f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"

    async def analyze_document_stream(
        self,
        document_id: int,
        analysis_type: str,
        user_id: int,
        question: Optional[str] = None,
        force_regenerate: bool = False,
        request=None,
        preferred_language: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream analysis response as SSE events.

        Reuses the same hardened pipeline as analyze_document() but streams
        LLM response chunks to the client via Server-Sent Events.

        Yields SSE-formatted strings:
        - data: {"type": "chunk", "content": "..."}\\n\\n
        - data: {"type": "citations", "citations": [...]}\\n\\n
        - data: {"type": "done", "analysis_id": 42}\\n\\n
        - data: {"type": "error", "message": "..."}\\n\\n

        Args:
            document_id: Document ID
            analysis_type: Type of analysis (summary, explanation, qa, lab_report, prescription)
            user_id: User ID (for authorization)
            question: User question (for QA)
            force_regenerate: Force regeneration, bypass cache
            request: FastAPI Request object (for client disconnect detection)
            preferred_language: User's UI language code (e.g., 'en', 'te', 'de').
                If set, the language is mandatory for the streamed response.

        Yields:
            SSE-formatted strings
        """
        session = get_db_session()
        try:
            # 1. Verify document exists and user has access
            document = session.execute(
                select(Document).where(Document.id == document_id, Document.user_id == user_id)
            ).scalar_one_or_none()

            if not document:
                yield self._sse_error("Document not found")
                return

            if document.status != "READY":
                yield self._sse_error(f"Document is not ready for analysis (status: {document.status})")
                return

            # 2. Parse chunks
            chunks = []
            if document.text_chunks:
                try:
                    chunks = json.loads(document.text_chunks)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse chunks for document {document_id}")
                    chunks = []

            if not chunks:
                yield self._sse_error("Document has no extracted text chunks")
                return

            # 3. Sanitize user question — prompt injection defense layer 1
            sanitized_question = None
            if question:
                sanitized_question = prompt_sanitizer.sanitize_question(question)
                is_safe, detected_pattern = prompt_sanitizer.is_question_safe(question)
                if not is_safe:
                    logger.warning(
                        "Prompt injection blocked in question for document %d: %s",
                        document_id, detected_pattern
                    )
                    yield self._sse_error(
                        f"Question contains potentially unsafe content and was blocked. "
                        f"Detected: {detected_pattern}"
                    )
                    return

            # 4. Build prompt (for cache key)
            prompt = self.prompt_builder.build_prompt(
                analysis_type=analysis_type,
                document_text=prompt_sanitizer.sanitize_text(
                    document.extracted_text or ""
                ),
                chunks=chunks,
                question=sanitized_question,
            )

            # 5. Generate prompt hash for cache key
            prompt_hash = self.cache._hash_prompt(prompt)

            # 6. Check cache (unless force regenerate)
            if not force_regenerate:
                cached = self.cache.get(document_id, analysis_type, prompt_hash, self.default_model)
                if cached:
                    logger.info(f"Returning cached analysis: document={document_id}, type={analysis_type}")
                    yield self._sse_chunk(cached["content"])
                    yield self._sse_citations(cached.get("citations", []))
                    yield self._sse_done(cached["id"])
                    return

            # 7. Select relevant chunks
            selected_chunks = self.context_selector.select_chunks(
                analysis_type=analysis_type,
                chunks=chunks,
                max_tokens=4000,
                question=sanitized_question,
            )

            # 8. Build final prompt with selected chunks
            final_prompt = self.prompt_builder.build_prompt(
                analysis_type=analysis_type,
                document_text=prompt_sanitizer.sanitize_text(
                    document.extracted_text or ""
                ),
                chunks=selected_chunks,
                question=sanitized_question,
            )

            # 9. Get system prompt (includes injection defense + mandatory language)
            system_prompt = self.prompt_builder.get_system_prompt(
                analysis_type,
                preferred_language=preferred_language or "",
            )

            # 10. Log the exact context that will be sent to the LLM
            self._log_llm_context(
                document, chunks, selected_chunks, final_prompt,
                self.default_model, analysis_type,
            )

            # 10. Call LLM with streaming
            logger.info(f"Generating streaming analysis: document={document_id}, type={analysis_type}, model={self.default_model}")
            start_time = time.time()

            accumulated_response = ""
            try:
                # NOTE: chat_async() is an async def (returns a coroutine),
                # not an async generator — it must be awaited before iterating.
                # Calling it without `await` yielded a coroutine and made
                # `async for` raise: "'async for' requires an object with
                # __aiter__ method, got coroutine".
                stream = await self.llm.chat_async(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": final_prompt},
                    ],
                    model=self.default_model,
                    stream=True,
                )
                async for chunk in stream:
                    accumulated_response += chunk
                    # Check for client disconnect
                    if request is not None:
                        try:
                            if await request.is_disconnected():
                                logger.info("Client disconnected, stopping stream for document %d", document_id)
                                return
                        except Exception:
                            pass
                    yield self._sse_chunk(chunk)
            except RuntimeError as e:
                logger.error(f"LLM streaming failed: {e}")
                yield self._sse_error(f"LLM generation failed: {e}")
                return

            latency = time.time() - start_time
            logger.info(f"Streaming analysis completed in {latency:.2f}s")

            # 11. Generate citations
            citations = self.citation_generator.generate_citations(selected_chunks, accumulated_response)

            # 12. Filter LLM output — prompt injection defense layer 5
            filtered = output_filter.filter_response(
                response=accumulated_response,
                analysis_type=analysis_type,
                source_text=document.extracted_text or "",
            )

            safe_response = filtered["content"]

            if filtered["warnings"]:
                for warning in filtered["warnings"]:
                    logger.warning("Output filter warning for analysis %d: %s", document_id, warning)

            if filtered["system_prompt_leaked"]:
                logger.error(
                    "System prompt leak detected and redacted in analysis for document %d",
                    document_id
                )

            # 13. Save to database
            analysis = DocumentAnalysis(
                document_id=document_id,
                type=analysis_type.upper(),
                content=safe_response,
                llm_model=self.default_model,
                prompt_hash=prompt_hash,
                citations=json.dumps(citations),
                generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                user_id=user_id,
            )
            session.add(analysis)
            session.commit()
            session.refresh(analysis)

            # 14. Cache result
            result = {
                "id": analysis.id,
                "type": analysis.type,
                "content": analysis.content,
                "citations": citations,
                "llm_model": analysis.llm_model,
                "generated_at": analysis.generated_at,
                "cached": False,
                "latency": latency,
                "warnings": filtered["warnings"],
                "system_prompt_leaked": filtered["system_prompt_leaked"],
                "disclaimer_added": filtered["disclaimer_added"],
            }
            self.cache.set(document_id, analysis_type, prompt_hash, self.default_model, result)

            logger.info(
                "Streaming analysis saved: id=%d, document=%d, type=%s, warnings=%d, leaked=%s, disclaimer=%s",
                analysis.id, document_id, analysis_type,
                len(filtered["warnings"]),
                filtered["system_prompt_leaked"],
                filtered["disclaimer_added"],
            )

            # 15. Yield citations + done
            yield self._sse_citations(citations)
            yield self._sse_done(analysis.id)

        except ValueError as e:
            yield self._sse_error(str(e))
        except Exception as e:
            session.rollback()
            logger.error(f"Streaming analysis failed: {e}")
            yield self._sse_error(f"Analysis failed: {e}")
        finally:
            session.close()

    async def get_analysis_history(
        self,
        document_id: int,
        user_id: int,
        analysis_type: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """
        Get analysis history for document.

        Args:
            document_id: Document ID
            user_id: User ID (for authorization)
            analysis_type: Filter by type (optional)
            page: Page number
            per_page: Items per page

        Returns:
            Dict with items, total, page, per_page
        """
        session = get_db_session()
        try:
            # Verify document exists and user has access
            document = session.execute(
                select(Document).where(Document.id == document_id, Document.user_id == user_id)
            ).scalar_one_or_none()

            if not document:
                raise ValueError("Document not found")

            # Build query
            query = select(DocumentAnalysis).where(DocumentAnalysis.document_id == document_id)

            if analysis_type:
                query = query.where(DocumentAnalysis.type == analysis_type.upper())

            # Count total
            from sqlalchemy import func
            count_query = select(func.count()).select_from(query.subquery())
            total = session.execute(count_query).scalar_one()

            # Paginate
            offset = (page - 1) * per_page
            query = query.order_by(DocumentAnalysis.generated_at.desc()).offset(offset).limit(per_page)

            analyses = session.execute(query).scalars().all()

            # Format results
            items = []
            for analysis in analyses:
                citations = []
                if analysis.citations:
                    try:
                        citations = json.loads(analysis.citations)
                    except json.JSONDecodeError:
                        pass

                items.append({
                    "id": analysis.id,
                    "type": analysis.type,
                    "content": analysis.content,
                    "citations": citations,
                    "llm_model": analysis.llm_model,
                    "generated_at": analysis.generated_at,
                })

            return {
                "items": items,
                "total": total,
                "page": page,
                "per_page": per_page,
            }

        finally:
            session.close()

    async def delete_analysis(self, analysis_id: int, document_id: int, user_id: int) -> bool:
        """
        Delete specific analysis.

        Args:
            analysis_id: Analysis ID
            document_id: Document ID
            user_id: User ID (for authorization)

        Returns:
            True if deleted, False if not found
        """
        session = get_db_session()
        try:
            # Verify document exists and user has access
            document = session.execute(
                select(Document).where(Document.id == document_id, Document.user_id == user_id)
            ).scalar_one_or_none()

            if not document:
                raise ValueError("Document not found")

            # Get analysis
            analysis = session.execute(
                select(DocumentAnalysis).where(
                    DocumentAnalysis.id == analysis_id,
                    DocumentAnalysis.document_id == document_id,
                )
            ).scalar_one_or_none()

            if not analysis:
                return False

            # Delete from database
            session.delete(analysis)
            session.commit()

            # Invalidate cache for this document
            self.cache.invalidate_document(document_id)

            logger.info(f"Analysis deleted: id={analysis_id}, document={document_id}")
            return True

        finally:
            session.close()

    async def regenerate_analysis(
        self,
        analysis_id: int,
        document_id: int,
        user_id: int,
    ) -> dict:
        """
        Regenerate analysis (force new analysis).

        Args:
            analysis_id: Analysis ID to regenerate
            document_id: Document ID
            user_id: User ID (for authorization)

        Returns:
            New analysis result dict
        """
        session = get_db_session()
        try:
            # Verify document exists and user has access
            document = session.execute(
                select(Document).where(Document.id == document_id, Document.user_id == user_id)
            ).scalar_one_or_none()

            if not document:
                raise ValueError("Document not found")

            # Get old analysis
            old_analysis = session.execute(
                select(DocumentAnalysis).where(
                    DocumentAnalysis.id == analysis_id,
                    DocumentAnalysis.document_id == document_id,
                )
            ).scalar_one_or_none()

            if not old_analysis:
                raise ValueError("Analysis not found")

            # Store analysis type before deleting
            analysis_type = old_analysis.type

            # Delete old analysis
            session.delete(old_analysis)
            session.commit()

            # Invalidate cache
            self.cache.invalidate_document(document_id)

            # Generate new analysis
            logger.info(f"Regenerating analysis: document={document_id}, type={analysis_type}")
            result = await self.analyze_document(
                document_id=document_id,
                analysis_type=analysis_type,
                user_id=user_id,
                force_regenerate=True,
            )

            return result

        finally:
            session.close()


# Import here to avoid circular dependency
from sqlalchemy import select

# Global instance
analysis_service = AnalysisService()
