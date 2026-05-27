"""Deprecated: re-exports from ``app.services._shared.qa_kb.csv_utils``.

Kept for one release cycle so existing imports keep working while callers
migrate. New code should import from the shared module directly.
"""

from app.services._shared.qa_kb.csv_utils import (
    UnsupportedQaCsvError,
    _parse_csv_rows,
    extract_questions_from_csv,
    merge_csv_files,
    normalize_qa_csv_rows,
    split_qa_csv_by_image,
    validate_supported_hciot_csv,
)

__all__ = [
    "UnsupportedQaCsvError",
    "_parse_csv_rows",
    "extract_questions_from_csv",
    "merge_csv_files",
    "normalize_qa_csv_rows",
    "split_qa_csv_by_image",
    "validate_supported_hciot_csv",
]
