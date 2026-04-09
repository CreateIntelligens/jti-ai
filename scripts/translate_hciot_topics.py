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
    """Parse comma-separated strings like 'key1,name:key2' into GeminiKey objects."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    keys = []
    for i, part in enumerate(parts):
        if ":" in part:
            name, key = part.split(":", 1)
            keys.append(GeminiKey(name.strip(), key.strip()))
        else:
            keys.append(GeminiKey(f"Key #{i + 1}", part))
    return keys


def select_gemini_key(keys: list[GeminiKey], preferred_name: str) -> GeminiKey:
    if not keys:
        raise ValueError("GEMINI_API_KEYS is empty")
    
    hint = preferred_name.strip().lower()
    if hint:
        for key in keys:
            if hint in key.name.lower():
                return key
    return keys[0]


def request_json(url: str, method: str = "GET", headers: dict[str, str] | None = None, payload: Any = None) -> Any:
    request_headers = (headers or {}).copy()
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    
    request = Request(url, method=method, headers=request_headers, data=data)
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_topics(base_url: str) -> list[Topic]:
    url = f"{base_url.rstrip('/')}/api/hciot/topics"
    payload = request_json(url)
    return [t for cat in payload.get("categories", []) for t in cat.get("topics", [])]


def get_non_empty_en_questions(topic: Topic) -> list[str]:
    questions = topic.get("questions", {}).get("en", [])
    return [str(q).strip() for q in questions if str(q).strip()]


def should_translate(topic: Topic, overwrite: bool, allowed_ids: set[str]) -> bool:
    topic_id = str(topic.get("id") or topic.get("topic_id") or "").strip()
    if not topic_id:
        return False
    if allowed_ids and topic_id not in allowed_ids:
        return False
    if get_non_empty_en_questions(topic) and not overwrite:
        return False
    return True


def translate_questions(client: genai.Client, model: str, topic: Topic) -> list[str]:
    topic_id = str(topic.get("id") or topic.get("topic_id") or "").strip()
    zh_qs = topic.get("questions", {}).get("zh", [])
    
    prompt = (
        "Translate the following Traditional Chinese hospital FAQ questions into natural, patient-friendly English.\n"
        "Return JSON only with this shape: {\"en\": [\"...\", \"...\"]}\n"
        "Rules:\n"
        f"- Return exactly {len(zh_qs)} translated strings.\n"
        "- Keep the same order as the original list.\n"
        "- Preserve medical meaning accurately.\n"
        "- Use concise, natural hospital FAQ wording.\n"
        "- Do not add numbering, markdown, or commentary.\n\n"
        f"Category: {topic.get('category_labels', {}).get('zh', '')} / {topic.get('category_labels', {}).get('en', '')}\n"
        f"Topic: {topic.get('labels', {}).get('zh', '')} / {topic.get('labels', {}).get('en', '')}\n"
        f"topic_id: {topic_id}\n\n"
        f"Questions zh:\n{json.dumps(zh_qs, ensure_ascii=False, indent=2)}"
    )

    for attempt in range(TRANSLATION_RETRIES):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            data = json.loads(resp.text or "{}")
            english = [str(q).strip() for q in data.get("en", [])]
            
            if len(english) != len(zh_qs):
                raise ValueError(f"Count mismatch: expected {len(zh_qs)}, got {len(english)}")
            if any(not q for q in english):
                raise ValueError("Contains empty strings")
            
            return english
        except Exception as e:
            if attempt + 1 == TRANSLATION_RETRIES:
                raise e
            time.sleep(1 + attempt)
    return []


def main() -> int:
    load_dotenv()
    args = parse_args()

    admin_key = (os.getenv("ADMIN_API_KEY") or "").strip()
    if args.apply and not admin_key:
        print("error: ADMIN_API_KEY required for --apply", file=sys.stderr)
        return 1

    keys = parse_gemini_keys(os.getenv("GEMINI_API_KEYS", ""))
    selected = select_gemini_key(keys, args.key_name)
    client = genai.Client(api_key=selected.api_key)

    topics = fetch_topics(args.base_url)
    if args.backup_path:
        Path(args.backup_path).write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")

    allowed_ids = {t.strip() for t in args.topic_ids or [] if t.strip()}
    translated_data = []
    count = 0

    for topic in topics:
        if not should_translate(topic, args.overwrite, allowed_ids):
            continue
        if args.limit and count >= args.limit:
            break

        topic_id = str(topic.get("id") or topic.get("topic_id") or "").strip()
        zh_qs = topic.get("questions", {}).get("zh", [])
        
        print(f"[translate] {topic_id} ({len(zh_qs)} questions)")
        en_qs = translate_questions(client, args.model, topic)
        
        translated_topic = {
            "id": topic_id,
            "labels": topic.get("labels", {}),
            "category_labels": topic.get("category_labels", {}),
            "questions": {"zh": zh_qs, "en": en_qs},
        }
        translated_data.append(translated_topic)

        if args.apply:
            url = f"{args.base_url.rstrip('/')}/api/hciot-admin/topics/{quote(topic_id, safe='/')}"
            request_json(url, method="PUT", headers={"API-Token": admin_key}, payload={"questions": {"zh": zh_qs, "en": en_qs}})
            print(f"[updated] {topic_id}")

        count += 1

    if args.output_path:
        Path(args.output_path).write_text(json.dumps(translated_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"processed topics: {count}")
    print(f"mode: {'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"fatal error: {error}", file=sys.stderr)
        sys.exit(1)
