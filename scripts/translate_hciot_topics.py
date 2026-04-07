#!/usr/bin/env python3
"""Translate HCIoT topic questions into English and write them back via admin API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from google import genai
from google.genai import types


Topic = dict[str, Any]


DEFAULT_BASE_URL = "http://localhost:8913"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_KEY_NAME_HINT = "護聯HCIOT"
REQUEST_TIMEOUT_SECONDS = 60
TRANSLATION_RETRIES = 3


@dataclass
class GeminiKey:
    name: str
    api_key: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Target API base URL")
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL))
    parser.add_argument("--key-name", default=DEFAULT_KEY_NAME_HINT, help="Preferred Gemini key label")
    parser.add_argument("--topic-id", action="append", dest="topic_ids", help="Only translate these topic ids")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of topics to process")
    parser.add_argument("--apply", action="store_true", help="Write translations back through admin API")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing non-empty English question lists")
    parser.add_argument("--backup-path", help="Write fetched source topics JSON to this path")
    parser.add_argument("--output-path", help="Write translated topics JSON to this path")
    return parser.parse_args()


def parse_gemini_keys(raw: str) -> list[GeminiKey]:
    keys: list[GeminiKey] = []
    for index, token in enumerate(part.strip() for part in raw.split(",") if part.strip()):
        if ":" in token:
            name, api_key = token.split(":", 1)
            keys.append(GeminiKey(name=name.strip(), api_key=api_key.strip()))
            continue
        keys.append(GeminiKey(name=f"Key #{index + 1}", api_key=token.strip()))
    return keys


def select_gemini_key(keys: list[GeminiKey], preferred_name: str) -> GeminiKey:
    if not keys:
        raise ValueError("GEMINI_API_KEYS is empty after loading .env")
    preferred_name = preferred_name.strip().lower()
    if preferred_name:
        for key in keys:
            if preferred_name in key.name.lower():
                return key
    return keys[0]


def build_api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def get_topic_id(topic: Topic) -> str:
    return str(topic.get("id") or topic.get("topic_id") or "").strip()


def get_question_list(topic: Topic, language: str) -> list[str]:
    return list(topic.get("questions", {}).get(language, []))


def build_translated_topic(
    topic_id: str,
    topic: Topic,
    zh_questions: list[str],
    en_questions: list[str],
) -> Topic:
    return {
        "id": topic_id,
        "labels": topic.get("labels", {}),
        "category_labels": topic.get("category_labels", {}),
        "questions": {"zh": zh_questions, "en": en_questions},
    }


def get_non_empty_english_questions(topic: Topic) -> list[str]:
    return [str(item).strip() for item in get_question_list(topic, "en") if str(item).strip()]


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, method=method, headers=request_headers, data=body)
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_topics(base_url: str) -> list[Topic]:
    payload = request_json(build_api_url(base_url, "/api/hciot/topics"))
    return [
        topic
        for category in payload.get("categories", [])
        for topic in category.get("topics", [])
    ]


def should_translate_topic(topic: Topic, overwrite: bool, allowed_topic_ids: set[str]) -> bool:
    topic_id = get_topic_id(topic)
    if not topic_id:
        return False
    if allowed_topic_ids and topic_id not in allowed_topic_ids:
        return False
    if get_non_empty_english_questions(topic) and not overwrite:
        return False
    return True


def build_translation_prompt(topic: Topic) -> str:
    labels = topic.get("labels", {})
    category_labels = topic.get("category_labels", {})
    topic_id = get_topic_id(topic)
    zh_questions = get_question_list(topic, "zh")
    return (
        "Translate the following Traditional Chinese hospital FAQ questions into natural, patient-friendly English.\n"
        "Return JSON only with this shape: {\"en\": [\"...\", \"...\"]}\n"
        "Rules:\n"
        f"- Return exactly {len(zh_questions)} translated strings.\n"
        "- Keep the same order as the original list.\n"
        "- Preserve medical meaning accurately.\n"
        "- Use concise, natural hospital FAQ wording.\n"
        "- Do not add numbering, markdown, or commentary.\n"
        "- If the source says 圖示, translate it naturally as '(with illustration)'.\n\n"
        f"Category zh: {category_labels.get('zh', '')}\n"
        f"Category en: {category_labels.get('en', '')}\n"
        f"Topic zh: {labels.get('zh', '')}\n"
        f"Topic en: {labels.get('en', '')}\n"
        f"topic_id: {topic_id}\n\n"
        f"Questions zh:\n{json.dumps(zh_questions, ensure_ascii=False, indent=2)}"
    )


def translate_questions(client: genai.Client, model: str, topic: Topic) -> list[str]:
    topic_id = get_topic_id(topic)
    zh_questions = get_question_list(topic, "zh")
    prompt = build_translation_prompt(topic)
    last_error: Exception | None = None
    for attempt in range(TRANSLATION_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            text = (response.text or "").strip()
            payload = json.loads(text)
            english = payload.get("en")
            if not isinstance(english, list):
                raise ValueError(f"Missing 'en' list in translation payload: {text[:200]}")
            translated = [str(item).strip() for item in english]
            if len(translated) != len(zh_questions):
                raise ValueError(
                    f"Translation count mismatch for {topic_id}: expected {len(zh_questions)}, got {len(translated)}"
                )
            if any(not item for item in translated):
                raise ValueError(f"Translation contains empty strings for {topic_id}")
            return translated
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt + 1 < TRANSLATION_RETRIES:
                time.sleep(1.0 + attempt)
                continue
    assert last_error is not None
    raise last_error


def update_topic_questions(base_url: str, admin_api_key: str, topic_id: str, zh_questions: list[str], en_questions: list[str]) -> Any:
    escaped_topic_id = quote(topic_id, safe="/")
    return request_json(
        build_api_url(base_url, f"/api/hciot-admin/topics/{escaped_topic_id}"),
        method="PUT",
        headers={"API-Token": admin_api_key},
        payload={"questions": {"zh": zh_questions, "en": en_questions}},
    )


def write_json(path_str: str, payload: Any) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv()
    args = parse_args()

    admin_api_key = (os.getenv("ADMIN_API_KEY") or "").strip()
    if args.apply and not admin_api_key:
        raise ValueError("ADMIN_API_KEY is required for --apply")

    gemini_keys = parse_gemini_keys(os.getenv("GEMINI_API_KEYS", ""))
    selected_key = select_gemini_key(gemini_keys, args.key_name)
    client = genai.Client(api_key=selected_key.api_key)

    topics = fetch_topics(args.base_url)
    if args.backup_path:
        write_json(args.backup_path, topics)

    allowed_topic_ids = {topic_id.strip() for topic_id in args.topic_ids or [] if topic_id.strip()}
    translated_topics: list[Topic] = []
    processed_count = 0

    for topic in topics:
        if not should_translate_topic(topic, args.overwrite, allowed_topic_ids):
            continue
        if args.limit and processed_count >= args.limit:
            break

        topic_id = get_topic_id(topic)
        zh_questions = get_question_list(topic, "zh")
        print(f"[translate] {topic_id} ({len(zh_questions)} questions)")
        en_questions = translate_questions(client, args.model, topic)
        translated_topics.append(build_translated_topic(topic_id, topic, zh_questions, en_questions))

        if args.apply:
            update_topic_questions(args.base_url, admin_api_key, topic_id, zh_questions, en_questions)
            print(f"[updated] {topic_id}")

        processed_count += 1

    if args.output_path:
        write_json(args.output_path, translated_topics)

    print(f"processed topics: {processed_count}")
    print(f"mode: {'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
