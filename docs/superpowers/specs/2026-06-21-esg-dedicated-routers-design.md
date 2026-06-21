# 為 ESG 建立專屬門牌(chat / prompts / quiz / quiz_bank)

**狀態:** Draft
**日期:** 2026-06-21

## 背景

ESG 目前的 chat / prompts / quiz / quiz_bank 都透過 **general 共用門牌**運作
(`/api/chat`、`/api/stores/__esg__/prompts`、`/api/general/quiz-bank/__esg__/*`),
靠 `store_name=__esg__` 動態解析,**沒有專屬 URL**,也沒有 `app/services/esg/`
專屬層——persona/session 走 general 的動態機制。

JTI 與 HCIoT 則有**專屬門牌 + 專屬 service 層**:
- JTI:`/api/jti/*`,完整四件(chat+prompts+quiz+quiz_bank),`app/services/jti/*`。
- HCIoT:`/api/hciot/*`,chat+prompts(無 quiz),`app/services/hciot/*`。

**目標**:給 ESG 也建一套完整專屬層,對齊 JTI——專屬門牌 `/api/esg/*`,涵蓋
chat + prompts + quiz + quiz_bank,背後是 `app/services/esg/*` 注入 ESG config,
共用 general 引擎(`ManagedChatService` / `ManagedQuizService` / `ManagedAppAgent`)。

## 設計決策(已確認)

- 範圍:**全部四件** chat + prompts + quiz + quiz_bank。
- 背後:**完整專屬層**(像 jti/hciot),不只是薄轉呼共用 general 動態機制。

## 現況依賴盤點(已查證)

| 元件 | jti 現有 | esg 現況 | esg 需新建 |
|---|---|---|---|
| router 薄殼 | `routers/jti/{chat,prompts,quiz,quiz_bank}.py` | 只有 `knowledge.py` | 4 個薄殼 |
| service 層 | `services/jti/*` | **無 `services/esg/`** | 新建整層 |
| `main_agent` | `MainAgent(ManagedAppAgent)` + `JTI_AGENT_CONFIG` | 走 general 動態 | `services/esg/main_agent.py` |
| persona | `services/jti/agent_prompts.py`(PERSONA、模板) | 走 general 動態(prompt manager) | `services/esg/agent_prompts.py`(寫死 ESG persona) |
| runtime settings | `services/jti/runtime_settings.py` | 走 general | `services/esg/runtime_settings.py` |
| quiz config | `services/jti/quiz_flow.py`(`JTI_QUIZ_CONFIG`) | — | `services/esg/quiz_flow.py`(`ESG_QUIZ_CONFIG`) |
| session/conversation manager | `deps.get_jti_session_manager` 等 | **deps 無 esg** | deps 加 esg manager |
| TTS | `get_managed_tts_job_manager("jti")` | — | 視 ESG 是否需 TTS;預設**不加**(esg 無 persona TTS 需求) |
| quiz store name 常數 | `JTI_STORE_NAME` in `quiz/config.py` | — | 加 `ESG_STORE_NAME = "__esg__"`;`mode` 列舉加 `"esg"` |
| 題庫資料 | — | `quiz_bank_esg_zh.json` 已遷移至 `__esg__` | 沿用,不需新建 |

## 實作策略(四階段)

### 階段 0｜共用層擴充(quiz config)

- `quiz/config.py`:加 `ESG_STORE_NAME = "__esg__"`;`QuizFlowConfig.mode`
  允許 `"esg"`。
- 確認 `ManagedAppAgentConfig` / `ManagedChatConfig` / `QuizFlowConfig` 的
  既有參數足以表達 ESG(jti/hciot 已驗證可參數化,風險低)。

### 階段 1｜建 `app/services/esg/` 專屬層

照 jti 範本各建一份,注入 ESG 值:
- `agent_prompts.py`:ESG persona(中/英)、session state 模板、
  `build_system_instruction`。**persona 內容需與現行 general 動態 persona 對齊**
  (從現有 `__esg__` prompt manager 既有設定取得,避免行為漂移)。
- `runtime_settings.py`:ESG runtime settings(回覆規則等)。
- `main_agent.py`:`EsgMainAgent(ManagedAppAgent)` + `ESG_AGENT_CONFIG`
  (`app="esg"`、`store_name_for_language` → `__esg__`/`__esg__en`、
  `rag_source_type="esg_knowledge"`)。
- `quiz_flow.py`:`ESG_QUIZ_CONFIG`(`store_name=__esg__`、`mode="esg"`)。

### 階段 2｜deps 加 ESG manager

- `deps.py`:加 `get_esg_session_manager`、`get_esg_conversation_logger`
  (照 jti/hciot 模式);啟動 warmup 區塊一併加入。
- TTS 預設不加(若 ESG 決定要語音,再循 `MANAGED_TTS_CONFIGS` 加 `"esg"`)。

### 階段 3｜建 4 個 router 薄殼並掛載(專屬門牌)

照 jti 範本:
- `routers/esg/chat.py`:`/api/esg/chat/start`、`/chat/message`、歷史/匯出
  (含 `compat_history` / `admin_history` 多 router,權限循 jti 的
  `require_history_access("esg")` / `verify_admin`)。
- `routers/esg/quiz.py`:`/api/esg/quiz/start`、`/quiz/pause`,用
  `ManagedQuizService(ESG_QUIZ_CONFIG)`。
- `routers/esg/prompts.py`:用 `_shared/persona_router.build_persona_router`,
  config 指向 `__esg__`/`__esg__en`、ESG persona。
- `routers/esg/quiz_bank.py`:循 jti 的 quiz_bank router,store 指向 `__esg__`。
- `main.py`:include 上述 router,prefix `/api/esg`、`/api/esg-admin/*`,
  與 jti 對稱(`include_in_schema` 等比照)。

## 端點對照(目標)

| 能力 | 新增專屬門牌 | 對應 jti |
|---|---|---|
| chat | `/api/esg/chat/start` `/chat/message` `/history` `/history/export` | `/api/jti/chat/*` |
| quiz | `/api/esg/quiz/start` `/quiz/pause` | `/api/jti/quiz/*` |
| prompts | `/api/esg-admin/prompts/*`(+ `/api/esg/prompts` 隱藏相容) | `/api/jti-admin/prompts/*` |
| quiz_bank | `/api/esg-admin/quiz-bank/*`(+ 隱藏相容) | `/api/jti-admin/quiz-bank/*` |
| knowledge | `/api/esg/knowledge`(已存在) | `/api/jti/knowledge` |

## 基準(已匯出)

現行 `__esg__` / `__esg__en` 的 prompt manager 設定已匯出至
`docs/superpowers/specs/baselines/2026-06-21-esg-prompt-baseline.json`。關鍵事實:

- **esg 沒有任何自訂 persona**:`prompts: []`、`active_prompt_id: null`——目前用
  系統預設 persona,沒有可漂移的自訂內容。
- **quiz 設定齊全且必須原樣保留**:
  - `quiz_enabled: true`
  - `quiz_start_keywords: ["測驗", "quiz", "問答"]`
  - `quiz_negative_keywords: []`
  - `quiz_copy.opening` / `already_done`(三立永續主題,中英雙語)

## 風險

- **persona 漂移(風險已降低)**:esg 無自訂 persona,只要新專屬層的預設 persona
  與現行系統預設一致即可,不需搬移自訂內容。真正要原樣保留的是上述 **quiz 設定**
  (keywords + copy),`ESG_QUIZ_CONFIG` 與 esg runtime settings 需帶入這些值。
- **共用門牌並存**:新增專屬門牌後,舊的共用門牌(`/api/chat` + `__esg__`)是否
  保留並存、或導引前端改用專屬門牌?需與前端確認(預設並存,不破壞既有呼叫)。
- **session 機制切換**:從 general 動態 session 改為 esg 專屬 session manager,
  需確認既有進行中的 esg 對話不受影響(預設新 session 才走新機制)。

## 非目標(YAGNI)

- 不改 jti / hciot 既有行為。
- 不移除既有 general 共用門牌(除非前端確認可下線)。
- ESG TTS 預設不做。
- 不改前端 UI 外觀;前端是否改打專屬門牌另議。
