"""One-off seeder: import ESG quiz banks into the two general ESG stores.

General stores have no boot-time seed path (store ids are dynamic hashes),
so this script mirrors the JTI seed logic (migrate_quiz_bank) but targets the
ESG stores explicitly and runs on demand.

Run inside the backend container:
    docker compose exec -T backend python scripts/seed_esg_quiz.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import app.deps as deps
from app.services.jti.quiz_bank_store import get_quiz_bank_store, DEFAULT_BANK_ID
from app.services.jti.quiz_results_store import get_quiz_results_store, DEFAULT_SET_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_esg_quiz")

# display_name -> real store_name (hashed). Both stores get zh + en banks so a
# session that switches language still finds questions (quiz_flow reads bank by
# session.language).
ESG_STORES = {
    "ESG_ZH": "store_95028fc06029",
    "ESG_EN": "store_b66923e91295",
}

BANK_JSON = {
    "zh": Path("data/quiz_bank_esg_zh.json"),
    "en": Path("data/quiz_bank_esg_en.json"),
}

# Single-dimension correct/wrong quiz: total score == number of correct answers.
DIMENSIONS = ["correct"]

# ESG asks ONE random question per run (JTI asks 4). Driven by selection_rules.total.
QUESTIONS_PER_RUN = 1

# ESG-specific copy so the quiz opening isn't the JTI "命定保護殼" fallback.
QUIZ_COPY = {
    "opening": {
        "zh": "來測測你對三立永續的了解吧！請選出正確答案：",
        "en": "Test your knowledge of SET's sustainability journey! Pick the correct answer:",
    },
    "already_done": {
        "zh": "你已經作答過囉！想再玩一次請重新整理頁面開始新的對話。",
        "en": "You've already answered! Refresh the page to start a new session.",
    },
}

# correct/wrong quizzes have one summary result keyed by the only dimension.
RESULTS = {
    "zh": {
        "correct": {
            "title": "ESG 永續達人",
            "description": "恭喜完成三立 ESG 永續問答！你對三立的永續足跡相當了解，一起共創台灣的美好永續。",
        }
    },
    "en": {
        "correct": {
            "title": "ESG Sustainability Expert",
            "description": "Congrats on completing the SET ESG quiz! You know SET's sustainability journey well. Let's co-create a better, greener Taiwan.",
        }
    },
}


def _load_bank(lang: str) -> dict:
    path = BANK_JSON[lang]
    data = json.load(open(path, encoding="utf-8"))
    # JSON uses the JTI quiz_sets container; take the single bank inside.
    bank = next(iter(data["quiz_sets"].values()))
    return bank


def _bank_metadata(bank: dict, questions: list[dict]) -> dict:
    return {
        "name": bank.get("name", "ESG Quiz"),
        "title": bank.get("name", ""),
        "description": bank.get("description", ""),
        "total_questions": QUESTIONS_PER_RUN,
        "dimensions": DIMENSIONS,
        "tie_breaker_priority": DIMENSIONS,
        # Ask one random question per run (JTI asks 4).
        "selection_rules": {"total": QUESTIONS_PER_RUN},
        "is_default": True,
    }


def seed() -> None:
    if deps.prompt_manager is None:
        deps.init_managers()

    bank_store = get_quiz_bank_store()
    results_store = get_quiz_results_store()
    bank_store._ensure_indexes()
    results_store._ensure_indexes()

    for display_name, store_name in ESG_STORES.items():
        for lang in ("zh", "en"):
            bank = _load_bank(lang)
            questions = bank["questions"]

            # --- quiz bank (mirror JTI: upsert meta -> activate -> replace qs) ---
            bank_store.upsert_metadata(
                lang, DEFAULT_BANK_ID, _bank_metadata(bank, questions), store_name=store_name
            )
            # Activate unconditionally: set_active_bank verifies the meta exists.
            # (get_metadata resolves the *active* bank, which isn't set yet.)
            bank_store.set_active_bank(lang, DEFAULT_BANK_ID, store_name=store_name)
            n = bank_store.replace_all_questions(
                lang, DEFAULT_BANK_ID, questions, store_name=store_name
            )

            # --- quiz results (mirror JTI: upsert set meta -> replace results) ---
            results_store.upsert_set_metadata(
                lang,
                DEFAULT_SET_ID,
                {"name": "ESG 預設結果" if lang == "zh" else "ESG Default Results",
                 "is_active": True, "is_default": True},
                store_name=store_name,
            )
            r = results_store.replace_all_results(
                lang, RESULTS[lang], set_id=DEFAULT_SET_ID, store_name=store_name
            )
            logger.info(
                "[ESG seed] %s (%s) lang=%s: %d questions, %d results",
                display_name, store_name, lang, n, r,
            )

    # --- enable quiz on the prompt config so chat actually triggers it ---
    pm = deps.prompt_manager
    for store_name in ESG_STORES.values():
        sp = pm.get_store_prompts(store_name)
        sp.quiz_enabled = True
        if "測驗" not in sp.quiz_start_keywords:
            sp.quiz_start_keywords = list(sp.quiz_start_keywords) + ["測驗", "quiz", "問答"]
        sp.quiz_copy = QUIZ_COPY
        pm.save_store_prompts(sp)
        logger.info("[ESG seed] quiz_enabled=True for %s (kw=%s)", store_name, sp.quiz_start_keywords)


if __name__ == "__main__":
    seed()
