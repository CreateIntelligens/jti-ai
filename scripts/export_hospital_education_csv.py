from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
IMAGE_TOKEN_RE = re.compile(r"^\[\[IMG::(.+?)\]\]$")
QUESTION_RE = re.compile(r"^Q\s*(\d+)\s*[：:]?\s*(.*)$")
ANSWER_RE = re.compile(r"^A\s*[：:]\s*(.*)$")
INLINE_ANSWER_RE = re.compile(r"\s*A\s*[：:]\s*", re.UNICODE)
RASTER_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


@dataclass
class QaRow:
    topic: str
    order: int
    source_question_no: str
    question: str
    answer_parts: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)

    @property
    def index(self) -> str:
        return f"{self.topic}_{self.order:03d}"

    @property
    def answer(self) -> str:
        return "\n".join(part for part in self.answer_parts if part).strip()

    @property
    def row_id(self) -> str:
        return self.index


def normalize_inline_text(value: str) -> str:
    value = value.replace("\ufeff", " ").replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def tokenize_markdown(text: str) -> list[str]:
    prepared = IMAGE_MARKDOWN_RE.sub(lambda match: f"\n[[IMG::{match.group(1)}]]\n", text)
    return [line.strip() for line in prepared.splitlines()]


def split_question_and_answer(value: str) -> tuple[str, str]:
    parts = INLINE_ANSWER_RE.split(value, maxsplit=1)
    if len(parts) == 2:
        return normalize_inline_text(parts[0]), normalize_inline_text(parts[1])
    return normalize_inline_text(value), ""


def iter_markdown_files(root: Path) -> list[Path]:
    markdown_files: list[Path] = []
    for topic_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        topic_file = topic_dir / f"{topic_dir.name}.md"
        if topic_file.exists():
            markdown_files.append(topic_file)
    return markdown_files


def parse_markdown_file(markdown_file: Path, root: Path) -> list[QaRow]:
    topic = markdown_file.parent.name
    rows: list[QaRow] = []
    pending_images: list[str] = []
    current: QaRow | None = None

    for raw_line in tokenize_markdown(markdown_file.read_text(encoding="utf-8")):
        if not raw_line or raw_line == "---":
            continue

        if raw_line.startswith("#"):
            continue

        image_match = IMAGE_TOKEN_RE.match(raw_line)
        if image_match:
            relative_image = resolve_image_relative_path(markdown_file, root, image_match.group(1))
            if not relative_image:
                continue
            if current is None:
                pending_images.append(relative_image)
            else:
                current.images.append(relative_image)
            continue

        question_match = QUESTION_RE.match(raw_line)
        if question_match:
            if current is not None:
                rows.append(current)

            source_question_no, remainder = question_match.groups()
            question_text, inline_answer = split_question_and_answer(remainder)
            current = QaRow(
                topic=topic,
                order=len(rows) + 1,
                source_question_no=source_question_no,
                question=question_text,
                images=pending_images.copy(),
            )
            pending_images.clear()
            if inline_answer:
                current.answer_parts.append(inline_answer)
            continue

        if current is None:
            continue

        answer_match = ANSWER_RE.match(raw_line)
        if answer_match:
            answer_text = normalize_inline_text(answer_match.group(1))
            if answer_text:
                current.answer_parts.append(answer_text)
            continue

        body_text = normalize_inline_text(raw_line)
        if body_text:
            current.answer_parts.append(body_text)

    if current is not None:
        rows.append(current)

    return rows


def sanitize_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    return token


def build_topic_code_map(rows: list[QaRow]) -> dict[str, str]:
    topics_in_order = list(dict.fromkeys(row.topic for row in rows))
    code_map: dict[str, str] = {}
    for idx, topic in enumerate(topics_in_order, 1):
        token = sanitize_token(topic)
        if token:
            code_map[topic] = token[:12]
        else:
            code_map[topic] = f"T{idx:02d}"
    return code_map


def stem_token(path: str) -> str:
    stem = Path(path).stem
    token = sanitize_token(stem)
    return token or "IMG"


def serial_token(path: str) -> str:
    stem = Path(path).stem
    match = re.search(r"(\d+)$", stem)
    if match:
        return match.group(1).zfill(3)
    token = stem_token(path)
    return token[-6:] if len(token) > 6 else token


def resolve_image_relative_path(markdown_file: Path, root: Path, image_ref: str) -> str | None:
    direct_path = markdown_file.parent / image_ref
    if direct_path.exists():
        return str(direct_path.relative_to(root))

    parent = direct_path.parent
    stem = direct_path.stem
    if not parent.exists():
        return None

    candidates = sorted(parent.glob(f"{stem}.*"), key=lambda p: p.name.lower())
    if not candidates:
        return None

    def _priority(path: Path) -> tuple[int, str]:
        ext = path.suffix.lower()
        if ext in RASTER_IMAGE_EXTENSIONS:
            return (0, ext)
        return (1, ext)

    chosen = sorted(candidates, key=_priority)[0]
    return str(chosen.relative_to(root))


def build_image_id_map(rows: list[QaRow]) -> dict[str, str]:
    image_paths = sorted({image_path for row in rows for image_path in row.images})
    topic_codes = build_topic_code_map(rows)
    image_id_map: dict[str, str] = {}
    used_ids: set[str] = set()

    for image_path in image_paths:
        parts = Path(image_path).parts
        topic = parts[0] if parts else ""
        topic_code = topic_codes.get(topic, "T00")
        base_id = f"IMG_{topic_code}_{serial_token(image_path)}"
        image_id = base_id
        suffix = 2
        while image_id in used_ids:
            image_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(image_id)
        image_id_map[image_path] = image_id

    return image_id_map


def build_export_image_name(image_path: str, image_id_map: dict[str, str]) -> str:
    image_id = image_id_map.get(image_path)
    suffix = Path(image_path).suffix.lower()
    if image_id:
        return f"{image_id}{suffix}"
    return Path(image_path).name


def copy_topic_images(topic_rows: list[QaRow], root: Path, target_images_dir: Path, image_id_map: dict[str, str]) -> None:
    if target_images_dir.exists():
        shutil.rmtree(target_images_dir)
    target_images_dir.mkdir(parents=True, exist_ok=True)

    used_image_paths = sorted({image_path for row in topic_rows for image_path in row.images})
    for image_path in used_image_paths:
        source_path = root / image_path
        if not source_path.exists():
            continue
        export_name = build_export_image_name(image_path, image_id_map)
        shutil.copy2(source_path, target_images_dir / export_name)


def write_csv(rows: list[QaRow], output_file: Path, image_path_builder, image_id_map: dict[str, str]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "index",
                "q",
                "a",
                "img",
            ],
        )
        writer.writeheader()
        for row in rows:
            image_refs: list[str] = []
            for image_path in row.images:
                image_id = image_id_map.get(image_path)
                image_ref = image_path_builder(image_path)
                if image_id:
                    image_refs.append(f"{image_id}={image_ref}")
                else:
                    image_refs.append(image_ref)
            writer.writerow(
                {
                    "index": row.index,
                    "q": row.question,
                    "a": row.answer,
                    "img": " | ".join(image_refs),
                }
            )


def export_csv(root: Path, output_root: Path) -> int:
    rows: list[QaRow] = []
    for markdown_file in iter_markdown_files(root):
        rows.extend(parse_markdown_file(markdown_file, root))

    image_id_map = build_image_id_map(rows)

    rows_by_topic: dict[str, list[QaRow]] = {}
    for row in rows:
        rows_by_topic.setdefault(row.topic, []).append(row)

    for topic, topic_rows in rows_by_topic.items():
        topic_dir = output_root / topic
        topic_csv = topic_dir / f"{topic}.csv"
        target_images_dir = topic_dir / "images"

        copy_topic_images(topic_rows, root, target_images_dir, image_id_map)

        write_csv(
            topic_rows,
            topic_csv,
            lambda image_path: f"images/{build_export_image_name(image_path, image_id_map)}",
            image_id_map,
        )

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export hospital education markdown files to CSV.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/home/human/jtai/.claude/醫院提供衛教資料/md"),
        help="Root directory that contains topic folders with markdown files.",
    )
    args = parser.parse_args()
    output_root = Path("/home/human/jtai/.claude/醫院提供衛教資料/csv")

    total_rows = export_csv(args.root, output_root)
    print(f"wrote {total_rows} rows to per-topic CSV files only")


if __name__ == "__main__":
    main()
