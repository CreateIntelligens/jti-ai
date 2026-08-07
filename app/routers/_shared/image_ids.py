"""Shared image_id normalization for knowledge-base image lookup.

CSV `img` 欄位的寫法與實際存檔名常有落差：Excel 匯出會帶副檔名或路徑、
同一張圖在不同來源可能寫成 ``PRP(1)`` / ``PRP (1)`` / ``PRP_1``，掃描檔名
又常多一層 ``IMG_`` 前綴。查圖時逐一嘗試這些等價寫法，避免為了遷就查詢
而在儲存層重複存好幾份同樣的圖。
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

__all__ = ["canonicalize_image_id", "candidate_image_ids"]


def canonicalize_image_id(image_id: str) -> str:
    """Single source of truth for image_id normalization, shared by GET-image
    lookup and reference counting so the two stay in sync."""
    return PurePosixPath(image_id).stem.replace(" ", "")


def _variants(value: str) -> list[str]:
    """Return equivalent spellings of a single candidate."""
    out = [
        value,
        re.sub(r"(\S)\(", r"\1 (", value),
        re.sub(r"\s*\((\d+)\)$", r"_\1", value),
    ]
    if match := re.match(r"^(.*?)_(\d+)$", value):
        stem, num = match.groups()
        out.extend((f"{stem}({num})", f"{stem} ({num})"))
    return out


def candidate_image_ids(image_id: str) -> list[str]:
    """Ordered, de-duplicated spellings to try when resolving an image id."""
    base = PurePosixPath(image_id).stem
    canonical = canonicalize_image_id(image_id)

    seen: set[str] = set()
    candidates: list[str] = []

    for candidate in (*_variants(base), *_variants(canonical)):
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)

        # Scanned filenames often carry an IMG_ prefix the CSV omits.
        if candidate.upper().startswith("IMG_") and len(candidate) > 4:
            stripped = candidate[4:]
            if stripped and stripped not in seen:
                seen.add(stripped)
                candidates.append(stripped)

    return candidates
