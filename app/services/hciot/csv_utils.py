"""
CSV utilities for HCIoT knowledge uploads.

Detects CSV files with a `q` column and extracts questions.
"""

from __future__ import annotations

import csv
import io


def extract_questions_from_csv(file_bytes: bytes) -> list[str] | None:
    """Extract question strings from a CSV with a ``q`` column.

    Returns a de-duplicated list of non-empty ``q`` values, or ``None``
    when the CSV has no ``q`` header (meaning it's a regular knowledge file).
    """
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "q" not in reader.fieldnames:
        return None

    seen: set[str] = set()
    questions: list[str] = []
    for row in reader:
        q = (row.get("q") or "").strip()
        if q and q not in seen:
            seen.add(q)
            questions.append(q)

    return questions if questions else None
