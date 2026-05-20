"""Normalize HCIoT English topic labels: underscores -> spaces, Title Case.

Background: VH-61 comment #13034 (Q3) — some EN topic `labels.en` values are
stored snake_case with underscores (e.g. "Department_Introductions") instead of
natural English ("Department Introductions").

Scope (deliberately conservative):
- Only documents with `language == "en"`.
- Only the `labels.en` field, and only when it contains an underscore.
- Acronyms in ACRONYMS keep their casing (e.g. "PRP").
- Does NOT touch: `labels.zh` (redundant garbage on EN docs), `category_labels`,
  `topic_id`, `questions`, or any ZH document.

Run inside the backend container (which has MONGODB_URI):
    docker compose cp scripts/normalize_hciot_en_labels.py backend:/tmp/n.py
    docker compose exec -T backend python /tmp/n.py            # dry-run preview
    docker compose exec -T backend python /tmp/n.py --apply    # write changes
"""

import os
import sys

from pymongo import MongoClient

# Tokens whose casing must be preserved verbatim instead of Title-cased.
ACRONYMS = {"PRP", "ICU", "ER", "CT", "MRI", "X-Ray"}


def normalize_label(value: str) -> str:
    """Underscores -> spaces, then Title Case each word (acronyms preserved)."""
    words = value.replace("_", " ").split()
    out = []
    for w in words:
        if w.upper() in {a.upper() for a in ACRONYMS}:
            # Reuse the canonical casing from ACRONYMS.
            out.append(next(a for a in ACRONYMS if a.upper() == w.upper()))
        else:
            out.append(w[:1].upper() + w[1:].lower() if w else w)
    return " ".join(out)


def main() -> None:
    apply = "--apply" in sys.argv

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise SystemExit("ERROR: MONGODB_URI not set")

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    coll = client["hciot_app"]["hciot_topics"]

    docs = list(coll.find({"language": "en"}, {"_id": 0, "topic_id": 1, "labels": 1}))
    changes = []
    for d in docs:
        labels = d.get("labels") or {}
        old = labels.get("en")
        if not isinstance(old, str) or "_" not in old:
            continue
        new = normalize_label(old)
        if new != old:
            changes.append((d["topic_id"], old, new))

    if not changes:
        print("No labels need normalization.")
        return

    print(f"{'APPLY' if apply else 'DRY-RUN'} — {len(changes)} label(s):")
    for topic_id, old, new in changes:
        print(f"  {topic_id}")
        print(f"    {old!r}  ->  {new!r}")

    if not apply:
        print("\nDry-run only. Re-run with --apply to write.")
        return

    modified = 0
    for topic_id, _old, new in changes:
        result = coll.update_one(
            {"language": "en", "topic_id": topic_id},
            {"$set": {"labels.en": new}},
        )
        modified += result.modified_count
    print(f"\nDone. modified={modified}")


if __name__ == "__main__":
    main()
