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


_FIELD_ALIASES: dict[str, list[str]] = {
    "q": ["q", "question", "問題", "问题", "題目", "题目"],
    "a": ["a", "answer", "答案", "回答", "回覆", "解答", "說明", "内容", "內容"],
    "img": ["img", "image", "圖片", "图片", "圖片 (image)", "image (圖片)"],
    "url": ["url", "link", "網址", "网址", "連結", "链接"],
    "index": ["index"],
}
_QA_CONTENT_FIELDS = ("q", "a", "img", "url")


def _normalize_fieldname(raw: str) -> str:
    key = raw.strip().lower()
    for canonical, aliases in _FIELD_ALIASES.items():
        if key in aliases:
            return canonical
    # Substring fallback only for multi-char aliases — single-letter aliases
    # like "q"/"a" would otherwise match unrelated headers ("category", "date").
    for canonical, aliases in _FIELD_ALIASES.items():
        if any(len(alias) >= 2 and alias in key for alias in aliases):
            return canonical
    return raw.strip()


def _parse_csv_rows(file_bytes: bytes) -> tuple[list[str], list[dict[str, str]]] | None:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return None

    fieldnames: list[str] = []
    first_raw_for: dict[str, str] = {}
    for raw in reader.fieldnames:
        canonical = _normalize_fieldname(raw)
        if canonical in first_raw_for:
            continue
        first_raw_for[canonical] = raw
        fieldnames.append(canonical)

    rows = [
        {canonical: row.get(first_raw_for[canonical], "") for canonical in fieldnames}
        for row in reader
    ]
    return fieldnames, rows


def _rows_to_csv_bytes(fieldnames: list[str], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _has_meaningful_qa_content(row: dict[str, str]) -> bool:
    return any((row.get(key) or "").strip() for key in _QA_CONTENT_FIELDS)


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


def normalize_qa_csv_rows(file_bytes: bytes) -> bytes | None:
    """Remove fully blank QA rows and backfill missing index values."""
    parsed = _parse_csv_rows(file_bytes)
    if parsed is None:
        return None

    fieldnames, rows = parsed
    if "q" not in fieldnames:
        return None

    if "index" not in fieldnames:
        fieldnames = ["index", *fieldnames]

    meaningful_rows = []
    i = 1
    for row in rows:
        if not _has_meaningful_qa_content(row):
            continue
        if not row.get("index"):
            row["index"] = str(i)
        meaningful_rows.append(row)
        i += 1

    return _rows_to_csv_bytes(fieldnames, meaningful_rows)


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
        if not _has_meaningful_qa_content(row):
            continue

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

    used_names: set[str] = {name for name, _ in uploads}
    for index, (row, img_value) in enumerate(image_rows, start=1):
        fragment = _image_filename_fragment(img_value, index)
        base = f"{path.stem}_{fragment}{suffix}"
        # Disambiguate when multiple rows share the same image fragment
        # (e.g. several Q&As referring to the same image) — otherwise these
        # would later get renamed to _1/_2 by the storage layer with no hint
        # of which row they came from.
        candidate = base
        counter = 1
        while candidate in used_names:
            stem = f"{path.stem}_{fragment}_row{index}"
            if counter > 1:
                stem = f"{stem}_{counter}"
            candidate = f"{stem}{suffix}"
            counter += 1
        used_names.add(candidate)
        uploads.append((candidate, _rows_to_csv_bytes(fieldnames, [row])))

    return uploads


def merge_csv_files(csv_contents: list[bytes], source_filenames: list[str] | None = None) -> list[dict]:
    """Parse multiple CSV bytes into unified list and sort by index.

    Returns a list of dicts with keys: index, q, a, img, url, source_file.
    When *source_filenames* is provided each row carries the filename it
    originated from so callers can map edits back to the correct file.
    """
    rows = []
    for idx, file_bytes in enumerate(csv_contents):
        parsed = _parse_csv_rows(file_bytes)
        if parsed is None:
            continue
        _, parsed_rows = parsed

        src = source_filenames[idx] if source_filenames and idx < len(source_filenames) else None

        for row in parsed_rows:
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
                "url": (row.get("url") or "").strip(),
                "source_file": src,
            }
            # Only add if there's non-meta content
            if any(merged_row[k] for k in _QA_CONTENT_FIELDS):
                rows.append(merged_row)

    def sort_key(item):
        raw = item["index"]
        try:
            return float(raw)
        except ValueError:
            return float("inf")

    rows.sort(key=sort_key)
    return rows
