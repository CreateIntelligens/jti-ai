# 將 JTI 遷移到 general 共用機制

**狀態:** Draft
**日期:** 2026-06-21

## 背景

`app/services/general/*` 與 `app/routers/general/*` 是已抽出的共用層,所有
managed app(ESG、HCIoT)都透過它運作——以 `store_name`(例如 `__esg__` /
`__esg__en`)動態解析 `managed_app` / `managed_language`,共用同一套 chat /
prompts / quiz_bank。

JTI 是**唯一還沒遷到 general 的特例**:它保有自己一整套
`app/routers/jti/*`(chat、prompts、quiz、quiz_bank)與
`app/services/jti/*`(main_agent、runtime_quiz_flow、quiz_helpers、
runtime_settings、tts…),繞過 general。

這造成兩套並行維護、行為易漂移。目標是把 JTI 收進 general,讓所有 app 統一。

**硬約束:對外端點不可變。** 前端目前打的所有 jti 路徑
(`/api/jti/chat`、`/api/jti/message`、`/api/jti/quiz`、`/api/jti-admin/prompts`、
`/api/jti/quiz-bank` 等,含 TTS 端點)必須**原封不動保留**,前端零改動。遷移是
「**換引擎不換門牌**」——保留 jti router 的 URL 與 request/response 形狀,只把
背後實作改為呼叫 general service。

## 現況盤點(已查證)

| 能力 | general | jti 專屬 | 備註 |
|---|---|---|---|
| chat `/start` `/message` `/history` | ✅ | ✅ | general 靠 `_resolve_request_store` → `resolve_store_config` 分 app |
| prompts/persona CRUD | ✅ | ✅ | general 用 `/{store_name}/prompts`;jti 用 `_shared/persona_router` |
| quiz_bank CRUD | ✅ | ✅ | |
| quiz 引擎(`runtime_quiz_flow`、`quiz_helpers`) | 反向重用 jti 的 | 本體在此 | `general/chat.py` 已 `from app.services.jti.runtime_quiz_flow import ...`,並用 `build_general_quiz_config` 將 persona/keywords 參數化 |
| **TTS** | 共用機制已存在 | jti 只是注入 config | `tts_utils.register_tts_endpoints(..., text_formatter=...)`、`tts_jobs.TtsJobManager`、`tts_text.prepare_tts_text` 都是共用層;jti/hciot 各自只有薄薄一個 `{app}/tts.py`(formatter + job manager wiring) |
| SessionStep 狀態機(WELCOME/QUIZ) | ✅(general chat 已處理 `session.step`) | ✅ | general `chat.py:344` 已用 `session.step.value` |

關鍵結論:quiz 引擎與 **TTS 都已是共用核心**——quiz 引擎檔案仍放在
`services/jti/` 下由 general 反向 import;TTS 則早已抽成 `tts_utils` /
`tts_jobs` / `tts_text`,jti 與 hciot 各自只留一個薄 `{app}/tts.py`
(`to_{app}_tts_text` + `get_{app}_tts_job_manager`)。因此 **general 不需要
「新長」任何能力**,整個遷移都是「搬家 + 注入 config」。TTS 的薄層形態正好就是
本遷移要套用的「共用 base + 各 app 薄 config」範本。

## 遷移策略(三階段)

### 階段 0｜搬家不改行為

把 general 反向依賴的 quiz 引擎從 `services/jti/` 移到共用位置:

- `app/services/jti/runtime_quiz_flow.py` → `app/services/general/quiz_runtime.py`
- `app/services/jti/quiz_helpers.py` → `app/services/general/quiz_helpers.py`

修正所有 import(general/chat.py、jti/chat.py、jti/quiz.py 等)。**零行為變更**,
只是讓「共用核心」名實相符。以既有測試驗證 jti 與 general 兩條路都仍正常。

### 階段 1｜在 general chat 注入既有 TTS 薄層(非新長能力)

TTS 共用機制(`tts_utils` / `tts_jobs` / `tts_text`)已存在且已參數化,本階段只是
把它接到 general chat:

**TTS 薄層收斂(已查證)**:`jti/tts.py` 與 `hciot/tts.py` 實質相同——
`to_{app}_tts_text` 都只是呼叫共用的 `prepare_tts_text(text, language)`;job
manager 只差三個值(character env 名、預設 character、`api_replacement`)。因此
兩個 `{app}/tts.py` 收斂成一個共用 factory:

```python
def make_tts_job_manager(app: str, env_var: str, default_char: str) -> TtsJobManager:
    character = (os.getenv(env_var, default_char).split(",")[0]).strip() or default_char
    return TtsJobManager(character=character, api_replacement=app)
```

- formatter 直接用共用 `prepare_tts_text`,不再各留一份。
- 採 hciot 版的 `.split(",")[0]` 解析(superset,對 jti 無副作用)。
- jti 注入 `("jti", "JTI_TTS_CHARACTER", "hayley")`;hciot 注入
  `("hciot", "HCIOT_TTS_CHARACTER", "healthy2")`,由 store config 帶入。

接法:general chat 透過 store config 取得 `(formatter, job_manager)`,沿用 hciot
既有 `register_tts_endpoints(..., text_formatter=...)` + `attach_tts_message_id`
的接法。沒帶 TTS 的 app(如 esg)維持無 TTS,行為不變。

hciot 已在用同一套 `tts_utils`,general 掛 TTS 可行性已被證實,風險低。本階段一併
拆掉 `jti/tts.py`、`hciot/tts.py` 兩個薄層(動到 hciot,需以 hciot TTS 測試驗證)。

### 階段 2｜抽 base class,jti router 改站在 base 上(端點不變)

實作形態是**抽 base class、開 API**:general 的 chat/quiz/prompts service 邏輯
收斂成共用 base class(或 router factory);jti **保留自己的薄 router**
(`routers/jti/*`,URL 與 request/response 形狀完全不動),只把背後實作從
`services/jti/*` 換成「繼承/組裝共用 base + 注入 jti 專屬 config」。

1. 把 general chat/quiz/prompts 的核心抽成 base class,以 config 注入差異點
   (persona、quiz copy/keywords/negative_keywords、TTS formatter 與 job
   manager)。general 與 jti 各自傳入自己的 config。
2. 確認 `__jti__` / `__jti__en` 的 store config(或注入給 base 的 config)帶齊
   jti 現在寫死的那組 persona、quiz keywords。
3. jti router 內部改呼叫 base class;**端點 URL 與 schema 維持不變**,前端零改動。
4. 驗證 chat / quiz / tts / prompts 全數通過後,刪除 `services/jti/*` 中已被
   base class 取代的重複實作(router 殼留著,因為門牌不能變)。

保留:jti router 殼(端點門牌)、jti 的 `knowledge.py`、migration scripts。

## 風險

- **JTI 在線上**:端點不變,但背後換引擎仍需可回滾;逐端點切換、保留舊實作直到驗證通過。
- **TTS 風險低**:共用 `tts_utils` 已參數化、hciot 已在用同一套,general 掛 TTS
  可行性已被證實。僅需確認 general session 能取得 store config 對應的 formatter
  與 job manager。
- **store config 完整性**:jti 寫死的 persona / quiz keywords 若沒完整遷入
  `__jti__` store config,切換後行為會漂移。階段 2 切換前需逐項比對。

## 非目標(YAGNI)

- 不重構 general 既有的 chat/prompts/quiz_bank 邏輯(TTS 也非新增,只是接上既有共用層)。
- 不動 ESG(已走 general,本次不碰)。**例外**:TTS 薄層收斂會改到
  `hciot/tts.py`(拆併成共用 factory),hciot 的對外行為不變,但需以 hciot TTS
  測試驗證。
- 不改前端 UI/後台介面外觀,端點 URL 與 schema 一律不變。
