#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

DEFAULT_URL = "https://www.ploom.tw/zh/support/faq"
DEFAULT_OUTPUT = Path(".claude/ploom_faq.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

FAQ_PATH_PATTERN = re.compile(r"/zh/support/faq/[a-z0-9-]+")
FAQ_ARTICLE_PATTERN = re.compile(
    r'\\"name\\":\\"FaqArticle\\",\\"options\\":\{\\"question\\":\\"(.*?)\\",.*?\\"answer\\":\\"(.*?)\\"\},\\"isRSC\\":null',
    flags=re.DOTALL,
)
FAQ_CATEGORY_PATTERN = re.compile(
    r'\\"name\\":\\"FaqCategory\\",\\"options\\":\{\\"title\\":\\"(.*?)\\",\\"slug\\":\\"(.*?)\\"',
    flags=re.DOTALL,
)

# Category mapping based on path patterns
CATEGORY_MAPPING = {
    "discover-ploom": "關於 Ploom",
    "benefits-and-usage": "關於 Ploom",
    "technology": "關於 Ploom",
    "ploom-x": "裝置保養",
    "tobacco-sticks": "菸彈",
    "sustainability": "菸彈",
    "accessories": "配件",
    "delivery": "訂單配送",
    "which-delivery-service": "訂單配送",
    "age-verificaton": "年齡驗證",
    "age-verification": "年齡驗證",
    "account-access": "帳戶註冊",
    "device-registration": "裝置註冊",
    "warranty-and-replacement": "裝置保固與更換",
    "ploom-care": "Ploom Care 團隊",
}


@dataclass(frozen=True)
class FaqItem:
    path: str
    question: str
    answer: str
    category: str = ""


def clean_text(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text)
    no_entities = unescape(no_tags)
    compact = re.sub(r"\s+", " ", no_entities).strip()
    return compact


def decode_escaped_json_string(value: str) -> str:
    # Values in self.__next_f payload are JSON-escaped string fragments.
    try:
        return json.loads('"' + value + '"')
    except json.JSONDecodeError:
        return value


def fetch_text(url: str, timeout: int = 20, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            },
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as err:
            last_error = err
            if attempt < retries:
                time.sleep(0.7 * attempt)
            continue

    assert last_error is not None
    raise last_error


def extract_categories_from_index(html: str) -> dict[str, str]:
    """Extract category mapping: slug -> title"""
    categories: dict[str, str] = {}
    for match in FAQ_CATEGORY_PATTERN.finditer(html):
        title_raw = decode_escaped_json_string(match.group(1))
        slug = match.group(2)
        title = clean_text(title_raw)
        categories[slug] = title
    return categories


def extract_paths_from_index(html: str) -> list[str]:
    # Preserve first-seen order and deduplicate.
    seen: set[str] = set()
    ordered: list[str] = []
    for path in FAQ_PATH_PATTERN.findall(html):
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def extract_faq_from_detail_html(path: str, html: str, categories: dict[str, str]) -> FaqItem | None:
    match = FAQ_ARTICLE_PATTERN.search(html)
    if not match:
        return None

    raw_question = decode_escaped_json_string(match.group(1))
    raw_answer_html = decode_escaped_json_string(match.group(2))

    question = clean_text(raw_question)
    answer = clean_text(raw_answer_html)

    if not question or not answer:
        return None

    # Extract category from path (e.g., /zh/support/faq/ploom-x-1 -> ploom-x)
    category_slug = ""
    path_parts = path.split("/")
    if len(path_parts) > 0:
        last_part = path_parts[-1]  # e.g., "ploom-x-1"
        # Remove trailing number (e.g., "ploom-x-1" -> "ploom-x")
        category_slug = re.sub(r"-\d+$", "", last_part)

    # First try to get from extracted categories, then fallback to mapping
    category = categories.get(category_slug, CATEGORY_MAPPING.get(category_slug, "其他"))

    return FaqItem(path=path, question=question, answer=answer, category=category)


def _fetch_and_extract_path(
    *,
    base_url: str,
    path: str,
    timeout: int,
    retries: int,
    categories: dict[str, str],
) -> tuple[str, FaqItem | None, str]:
    detail_url = urljoin(base_url, path)
    try:
        detail_html = fetch_text(detail_url, timeout=timeout, retries=retries)
    except (HTTPError, URLError, TimeoutError):
        return path, None, "fetch_failed"

    parsed = extract_faq_from_detail_html(path=path, html=detail_html, categories=categories)
    if parsed is None:
        return path, None, "article_missing"
    return path, parsed, "ok"


def extract_faq(url: str, timeout: int, retries: int, workers: int) -> tuple[list[FaqItem], dict[str, Any]]:
    index_html = fetch_text(url, timeout=timeout, retries=retries)
    categories = extract_categories_from_index(index_html)
    paths = extract_paths_from_index(index_html)

    faqs: list[FaqItem] = []
    failed_paths: list[str] = []
    missing_paths: list[str] = []
    seen_questions: set[str] = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [
            executor.submit(
                _fetch_and_extract_path,
                base_url=url,
                path=path,
                timeout=timeout,
                retries=retries,
                categories=categories,
            )
            for path in paths
        ]

        for future in concurrent.futures.as_completed(futures):
            path, parsed, status = future.result()
            if status == "fetch_failed":
                failed_paths.append(path)
                continue
            if status == "article_missing":
                missing_paths.append(path)
                continue
            if parsed is None:
                continue

            key = parsed.question.lower()
            if key in seen_questions:
                continue
            seen_questions.add(key)
            faqs.append(parsed)

    path_order = {path: idx for idx, path in enumerate(paths)}
    faqs.sort(key=lambda item: path_order.get(item.path, 10**9))
    failed_paths.sort(key=lambda p: path_order.get(p, 10**9))
    missing_paths.sort(key=lambda p: path_order.get(p, 10**9))

    debug: dict[str, Any] = {
        "method": "next_f_page_links_plus_detail_pages",
        "index_url": url,
        "paths_found": len(paths),
        "paths_failed": len(failed_paths),
        "paths_missing_article": len(missing_paths),
        "failed_paths": failed_paths,
        "missing_paths": missing_paths,
        "categories_found": len(categories),
        "categories": categories,
    }
    return faqs, debug


def write_output(path: Path, url: str, faqs: list[FaqItem], debug: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faq_count": len(faqs),
        "faqs": [
            {
                "path": item.path,
                "question": item.question,
                "answer": item.answer,
                "category": item.category,
            }
            for item in faqs
        ],
        "debug": debug,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_prompt_md(faqs: list[FaqItem]) -> str:
    """Generate prompt.md content from FAQs, grouped by category"""
    # Group FAQs by category
    categorized: dict[str, list[FaqItem]] = {}
    for faq in faqs:
        cat = faq.category or "其他"
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(faq)

    # Build markdown content
    lines = ["# Ploom X 常見問題", "", ""]

    for category, items in categorized.items():
        lines.append(f"## {category}")
        lines.append("")
        for item in items:
            lines.append(f"**Q: {item.question}**")
            lines.append("")
            lines.append(f"A: {item.answer}")
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def write_prompt_md(path: Path, faqs: list[FaqItem]) -> None:
    """Write prompt.md file"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_prompt_md(faqs)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape FAQ data from Ploom Taiwan support page.")
    parser.add_argument("--url", default=DEFAULT_URL, help="FAQ page URL")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output path (default: .claude/ploom_faq.json)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Per-request timeout seconds (default: 20)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retries per request on network failures (default: 3)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel workers for detail-page fetching (default: 8)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)

    faqs, debug = extract_faq(
        url=args.url,
        timeout=args.timeout,
        retries=args.retries,
        workers=args.workers,
    )
    write_output(output_path, args.url, faqs, debug)
    print(f"Saved {len(faqs)} FAQ items to {output_path}")

    # Also generate prompt.md
    prompt_md_path = output_path.parent / "ploom_faq.md"
    write_prompt_md(prompt_md_path, faqs)
    print(f"Generated FAQ markdown to {prompt_md_path}")


if __name__ == "__main__":
    main()
