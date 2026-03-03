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
            relative_image = str((markdown_file.parent / image_match.group(1)).relative_to(root))
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


def write_csv(rows: list[QaRow], output_file: Path, image_path_builder) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["index", "q", "a", "img"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "index": row.index,
                    "q": row.question,
                    "a": row.answer,
                    "img": " | ".join(image_path_builder(image_path) for image_path in row.images),
                }
            )


def export_csv(root: Path, output_file: Path) -> int:
    rows: list[QaRow] = []
    for markdown_file in iter_markdown_files(root):
        rows.extend(parse_markdown_file(markdown_file, root))

    write_csv(rows, output_file, lambda image_path: image_path)

    rows_by_topic: dict[str, list[QaRow]] = {}
    for row in rows:
        rows_by_topic.setdefault(row.topic, []).append(row)

    for topic, topic_rows in rows_by_topic.items():
        topic_dir = output_file.parent / topic
        topic_csv = topic_dir / f"{topic}.csv"
        source_images_dir = root / topic / "images"
        target_images_dir = topic_dir / "images"

        if source_images_dir.exists():
            shutil.copytree(source_images_dir, target_images_dir, dirs_exist_ok=True)

        write_csv(
            topic_rows,
            topic_csv,
            lambda image_path, topic=topic: str(Path(image_path).relative_to(topic)),
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
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/human/jtai/.claude/醫院提供衛教資料/csv/hospital_education_qa_index_img.csv"),
        help="Output CSV path.",
    )
    args = parser.parse_args()

    total_rows = export_csv(args.root, args.output)
    print(f"wrote {total_rows} rows to {args.output}")


if __name__ == "__main__":
    main()
