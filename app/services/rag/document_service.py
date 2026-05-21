import logging

from app.services.rag.backfill import get_backfill_service

logger = logging.getLogger(__name__)


class DocumentRagService:
    """Manages RAG operations specifically for non-QA general documents."""

    def __init__(self) -> None:
        self.backfill_service = get_backfill_service()

    @staticmethod
    def _source_type(app: str) -> str:
        return f"{app}_doc"

    def sync_document(self, app: str, language: str, filename: str, data: bytes) -> None:
        """Chunk and index a document into the app's document vector pool."""
        source_type = self._source_type(app)
        logger.info("[Document RAG] Syncing document: %s for app: %s, lang: %s", filename, app, language)
        try:
            self.backfill_service.index_single_file(
                source_type=source_type,
                language=language,
                filename=filename,
                data=data,
                force_text_chunking=True,
                force=True,
            )
        except Exception as e:
            logger.error("[Document RAG] Failed to sync document %s: %s", filename, e)
            raise

    def delete_document(self, app: str, language: str, filename: str) -> None:
        """Delete a document from the app's document vector pool."""
        source_type = self._source_type(app)
        logger.info("[Document RAG] Deleting document: %s for app: %s, lang: %s", filename, app, language)
        try:
            self.backfill_service.delete_from_rag(
                source_type=source_type,
                filename=filename,
                language=language,
            )
        except Exception as e:
            logger.error("[Document RAG] Failed to delete document %s: %s", filename, e)
            raise


_document_rag_service: DocumentRagService | None = None


def get_document_rag_service() -> DocumentRagService:
    global _document_rag_service
    if _document_rag_service is None:
        _document_rag_service = DocumentRagService()
    return _document_rag_service
