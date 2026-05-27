"""Deprecated: re-exports from ``app.services._shared.qa_kb.extract_jobs``.

Kept for one release cycle so existing imports keep working while callers
migrate. New code should import from the shared module directly.
"""

from app.services._shared.qa_kb.extract_jobs import (
    _JOBS,
    QaExtractJob,
    create_job,
    delete_job,
    get_job,
    prune_expired_jobs,
    update_job,
)

__all__ = [
    "_JOBS",
    "QaExtractJob",
    "create_job",
    "delete_job",
    "get_job",
    "prune_expired_jobs",
    "update_job",
]
