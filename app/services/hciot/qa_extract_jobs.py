"""In-memory job manager for HCIoT document-to-QA extraction tasks."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class QaExtractJob(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"]
    category_id: str | None = None
    topic_id: str | None = None
    category_label: str | None = None
    topic_label: str | None = None
    language: str
    qa_pairs: list[dict[str, str]] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Global in-memory job registry
_JOBS: dict[str, QaExtractJob] = {}


def create_job(
    job_id: str,
    category_id: str | None,
    topic_id: str | None,
    category_label: str | None,
    topic_label: str | None,
    language: str,
) -> QaExtractJob:
    """Create a new QA extraction job and save it in the memory registry."""
    prune_expired_jobs()
    job = QaExtractJob(
        job_id=job_id,
        status="pending",
        category_id=category_id,
        topic_id=topic_id,
        category_label=category_label,
        topic_label=topic_label,
        language=language,
    )
    _JOBS[job_id] = job
    return job


def get_job(job_id: str) -> QaExtractJob | None:
    """Retrieve a job by its ID, pruning expired ones first."""
    prune_expired_jobs()
    return _JOBS.get(job_id)


def update_job(job_id: str, **fields: Any) -> None:
    """Update field values of an existing job in the registry."""
    job = _JOBS.get(job_id)
    if not job:
        return

    for field, value in fields.items():
        if hasattr(job, field):
            setattr(job, field, value)


def delete_job(job_id: str) -> None:
    """Remove a job from the registry."""
    _JOBS.pop(job_id, None)


def prune_expired_jobs(max_age_hours: int = 1) -> None:
    """Prune jobs that are older than the specified age threshold to prevent memory bloating."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=max_age_hours)

    expired_ids = [
        job_id for job_id, job in _JOBS.items()
        if job.created_at < threshold
    ]

    for job_id in expired_ids:
        _JOBS.pop(job_id, None)
