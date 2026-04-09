"""
CSV utilities for HCIoT knowledge uploads.

Detects CSV files with a `q` column and extracts questions.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path


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


def _parse_csv_rows(file_bytes: bytes) -> tuple[list[str], list[dict[str, str]]] | None:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return None

    fieldnames = list(reader.fieldnames)
    rows = [{name: row.get(name, "") for name in fieldnames} for row in reader]
    return fieldnames, rows


def _rows_to_csv_bytes(fieldnames: list[str], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _split_image_name_and_suffix(raw: str) -> tuple[str, str]:
    value = raw.replace("\\", "/").split("/")[-1]
    if "." not in value:
        return value, ""

    stem, ext = value.rsplit(".", 1)
    clean_ext = re.sub(r"[^A-Za-z0-9]+", "", ext).lower()
    return stem, f".{clean_ext}" if clean_ext else ""


def _image_filename_fragment(raw: str, fallback_index: int) -> str:
    value = (raw or "").strip()
    if "=" in value:
        value = value.split("=", 1)[-1].strip()
    value, suffix = _split_image_name_and_suffix(value)
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or f"row_{fallback_index:03d}"
    value = value if value.upper().startswith("IMG_") else f"IMG_{value}"
    return f"{value}{suffix}"


def split_qa_csv_by_image(file_bytes: bytes, filename: str) -> list[tuple[str, bytes]] | None:
    """Split a QA CSV into a main file plus one-image-per-file CSVs.

    Returns ``None`` when the CSV is not a QA CSV or it has no non-empty
    ``img`` values, allowing callers to preserve the original single-file flow.
    """
    parsed = _parse_csv_rows(file_bytes)
    if parsed is None:
        return None

    fieldnames, rows = parsed
    if "q" not in fieldnames or "img" not in fieldnames:
        return None

    main_rows: list[dict[str, str]] = []
    image_rows: list[tuple[dict[str, str], str]] = []
    for row in rows:
        img_value = (row.get("img") or "").strip()
        if img_value:
            image_rows.append((row, img_value))
        else:
            main_rows.append(row)

    if not image_rows:
        return None

    path = Path(filename)
    suffix = path.suffix or ".csv"
    uploads: list[tuple[str, bytes]] = []

    if main_rows:
        uploads.append((path.name, _rows_to_csv_bytes(fieldnames, main_rows)))

    for index, (row, img_value) in enumerate(image_rows, start=1):
        fragment = _image_filename_fragment(img_value, index)
        uploads.append(
            (f"{path.stem}_{fragment}{suffix}", _rows_to_csv_bytes(fieldnames, [row]))
        )

    return uploads


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
