# Design — Extract QA Knowledge Base to Shared Layer

## Architecture Overview

```
app/
├── services/
│   ├── _shared/
│   │   ├── qa_kb/                            ← NEW
│   │   │   ├── __init__.py
│   │   │   ├── csv_utils.py                  ← moved from hciot
│   │   │   ├── extract_jobs.py               ← moved (in-memory job registry)
│   │   │   ├── extractor_base.py             ← LLM extraction flow (template injected)
│   │   │   ├── knowledge_store_base.py       ← Mongo CRUD with NAMESPACE injection point
│   │   │   ├── topic_store_base.py           ← Mongo CRUD with NAMESPACE injection point
│   │   │   └── prompts_loader.py             ← active persona/role_scope loader (attr names parameterised)
│   │   ├── agent_prompts_base.py             ← unchanged
│   │   └── runtime_settings_base.py          ← unchanged
│   ├── hciot/
│   │   ├── knowledge_store.py                ← becomes thin subclass setting NAMESPACE
│   │   ├── topic_store.py                    ← same
│   │   ├── qa_extractor.py                   ← keeps prompt template, delegates flow to base
│   │   ├── csv_utils.py                      ← DELETED (or re-export shim during transition)
│   │   ├── qa_extract_jobs.py                ← DELETED (or re-export shim)
│   │   └── agent_prompts.py                  ← keeps `get_active_persona_and_role_scope` thin wrapper
│   └── jti/                                  ← unchanged
└── routers/
    ├── _shared/
    │   └── qa_kb_router.py                   ← NEW: build_qa_kb_router(config) -> APIRouter
    └── hciot/
        ├── knowledge.py                      ← becomes thin: build config + include factory router
        └── qa_extract.py                     ← same
```

## Key Design Decisions

### 1. Store base classes — class hierarchy, not protocol

```python
# _shared/qa_kb/knowledge_store_base.py
class QaKbKnowledgeStoreBase:
    NAMESPACE: str = ""  # subclass must override
    COLLECTION_NAME: str = ""  # subclass must override

    def __init__(self):
        assert self.NAMESPACE, "subclass must set NAMESPACE"
        assert self.COLLECTION_NAME, "subclass must set COLLECTION_NAME"
        self.collection = mongo_client[self.COLLECTION_NAME]

    def insert_file(self, ...): ...
    def get_file(self, ...): ...
    def list_files(self, ...): ...
    def get_topic_csv_files(self, ...): ...
    # ... all the methods currently in HciotKnowledgeStore
```

```python
# hciot/knowledge_store.py
class HciotKnowledgeStore(QaKbKnowledgeStoreBase):
    NAMESPACE = "hciot"
    COLLECTION_NAME = "hciot_knowledge"
```

**Why class not protocol**: matches existing `app/services/_shared/agent_prompts_base.py` pattern, easier to share state (collection handle, language normalizer).

### 2. Router factory — closure over config object

```python
# _shared/qa_kb_router.py
@dataclass
class QaKbRouterConfig:
    tag: str                                  # e.g. "HCIoT Knowledge"
    auth_dep: Callable                        # verify_admin
    knowledge_store_factory: Callable         # get_hciot_knowledge_store
    topic_store_factory: Callable             # get_hciot_topic_store
    rag_source_type: str                      # "hciot"
    invalidate_cache: Callable                # invalidate_hciot_file_map
    persona_loader: Callable                  # get_active_persona_and_role_scope
    other_language: Callable                  # get_other_language

def build_qa_kb_router(config: QaKbRouterConfig) -> APIRouter:
    router = APIRouter(tags=[config.tag], dependencies=[Depends(config.auth_dep)])

    @router.post("/upload/")
    async def upload_knowledge_file(...): ...

    @router.post("/qa-extract")
    async def start_qa_extraction(...): ...

    # ... all current endpoints

    return router
```

```python
# routers/hciot/knowledge.py
from app.routers._shared.qa_kb_router import build_qa_kb_router, QaKbRouterConfig

router = build_qa_kb_router(QaKbRouterConfig(
    tag="HCIoT Knowledge",
    auth_dep=verify_admin,
    knowledge_store_factory=get_hciot_knowledge_store,
    ...
))
```

**Why factory not class**: FastAPI routers are not naturally subclass-friendly; closure over config is idiomatic FastAPI.

### 3. Extractor base — prompt as injected callable

```python
# _shared/qa_kb/extractor_base.py
async def extract_qa_from_document(
    *,
    text: str,
    language: str,
    persona_text: str,
    role_scope_text: str,
    build_instruction: Callable[[str, str, str], str],  # injected
    model_client: Any,
) -> list[dict[str, str]]:
    instruction = build_instruction(language, persona_text, role_scope_text)
    # ... LLM call, JSON parse, validation
```

```python
# hciot/qa_extractor.py
def _build_extraction_instruction(language, persona, scope): ...  # the long zh/en prompt

async def extract_qa_from_document(text, language="zh", persona_text="", role_scope_text=""):
    return await base_extract(
        text=text, language=language,
        persona_text=persona_text, role_scope_text=role_scope_text,
        build_instruction=_build_extraction_instruction,
        model_client=get_default_client(),
    )
```

### 4. Prompts loader — generic over attr names

```python
# _shared/qa_kb/prompts_loader.py
def load_active_persona_and_role_scope(
    *,
    language: str,
    store_name_for_language: Callable[[str], str],
    active_id_attr: str,
    persona_map_attr: str,
    runtime_map_attr: str,
    fallback_persona: str,
    fallback_role_scope: str,
) -> tuple[str, str]:
    """Generic active-prompt loader. Each sub-app supplies attr names + fallbacks."""
    # ... the cleaned-up version of the current hciot impl
```

```python
# hciot/agent_prompts.py
def get_active_persona_and_role_scope(language: str) -> tuple[str, str]:
    return load_active_persona_and_role_scope(
        language=language,
        store_name_for_language=lambda l: "__hciot__en" if l == "en" else "__hciot__",
        active_id_attr="hciot_active_prompt_id",
        persona_map_attr="hciot_persona_by_prompt",
        runtime_map_attr="hciot_runtime_settings_by_prompt",
        fallback_persona=PERSONA.get(language, PERSONA["zh"]),
        fallback_role_scope=DEFAULT_RESPONSE_RULE_SECTIONS.get(language, DEFAULT_RESPONSE_RULE_SECTIONS["zh"]).get("role_scope", ""),
    )
```

### 5. Backwards-compat shims during transition

For `csv_utils.py` and `qa_extract_jobs.py` that get *moved* (not split):

```python
# hciot/csv_utils.py  ← keep as shim for one release cycle
"""Deprecated: use app.services._shared.qa_kb.csv_utils instead."""
from app.services._shared.qa_kb.csv_utils import *  # noqa: F401,F403
```

So existing imports inside `hciot/` keep working until they're migrated in the same PR (or shortly after).

## Things That Stay in HCIoT

- `PERSONA`, `DEFAULT_RESPONSE_RULE_SECTIONS`, `WELCOME_TEXT`, `SESSION_STATE_TEMPLATES` (hciot-specific content)
- `_build_extraction_instruction` (long zh/en prompt with hospital terminology)
- `main_agent.py` (chat agent, not QA extraction)
- Image upload/admin (`images.py`, image picker UI) — couples too tightly to hciot UX
- `images_to_mongodb` migration script
- Quiz / TTS / runtime_settings (not in scope)

## Validation Strategy

After each stage commit, run the **HCIoT smoke checklist** (see tasks.md):

1. Upload a CSV with `q,a` columns → file appears in topic tree, Q&A 整合 shows rows
2. Upload a docx → AI extraction → preview → edit + toggle visible → import → check hidden_questions written correctly
3. Paste CSV text → preview → import → file in tree
4. Paste prose → AI extraction → same as #2
5. Upload duplicate (same q) → `skipped_all_duplicates: true`, no new doc
6. Delete file → topic sync, RAG sync
7. Edit Q&A 整合 → save → topic questions updated

Behavior must be **byte-for-byte identical** to pre-refactor.

## Open Questions

- 階段 4(router factory) 完成後,前端是否完全不需要動?**確認:不需要** — endpoint URL、form fields、response shape 全部一樣,只是後端內部換成 factory。
- 是否要保留 hciot 老 module 路徑當 deprecation shim?**Yes**, 一個 release cycle 後再清。

## Validation Plan (Per Stage)

每階段 commit 前:
1. Backend container 重啟成功(`docker compose up -d --force-recreate backend`)
2. `pytest tests/hciot/` 全綠
3. 手動 smoke test(見上)
4. Pyright 沒新 warning(現有 pre-existing 不算)
