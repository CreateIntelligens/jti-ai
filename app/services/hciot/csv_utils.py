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


def merge_csv_files(csv_contents: list[bytes], source_filenames: list[str] | None = None) -> list[dict]:
    """Parse multiple CSV bytes into unified list and sort by index.

    Returns a list of dicts with keys: index, q, a, img, source_file.
    When *source_filenames* is provided each row carries the filename it
    originated from so callers can map edits back to the correct file.
    """
    rows = []
    for idx, file_bytes in enumerate(csv_contents):
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            continue

        src = source_filenames[idx] if source_filenames and idx < len(source_filenames) else None

        for row in reader:
            # Clean image field: Excel exported CSVs often contain hyperlinks 
            # like 'IMG=images/photo.png' - extract just 'photo.png'
            img_val = (row.get("img") or "").strip()
            if "=" in img_val:
                img_val = img_val.split("=")[-1]
            if "/" in img_val:
                img_val = img_val.split("/")[-1]

            merged_row = {
                "index": (row.get("index") or "").strip(),
                "q": (row.get("q") or "").strip(),
                "a": (row.get("a") or "").strip(),
                "img": img_val,
                "source_file": src,
            }
            # Only add if there's non-meta content
            if any(merged_row[k] for k in ["q", "a", "img"]):
                rows.append(merged_row)

    def sort_key(item):
        raw = item["index"]
        try:
            return float(raw)
        except ValueError:
            return float("inf")

    rows.sort(key=sort_key)
    return rows
