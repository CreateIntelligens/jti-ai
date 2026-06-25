# HCIoT 前端：快速問答路徑前綴 + 圖片點擊放大

> Status: Draft
> Date: 2026-06-24
> Branch: feat/rag
> 範圍：純前端，兩個獨立小功能，合併一份 spec 一起做。後端不動。

## 功能 1：快速問答送出時帶上層級路徑前綴

### 現況
快速問答選單是 `category（分類）→ topic（主題）→ question（問題）` 三層
（`src/components/_shared/QaTopicGrid.tsx`，hciot 與 general 共用）。點 question chip 時
（`QaTopicGrid.tsx:95` `onClick={() => onSelectQuestion(question)}`）只送出 question 文字。

### 目標
送給 AI 的文字改成帶路徑前綴，讓 AI 有層級脈絡：
- 格式：`分類label/主題label：question`，例如 `常見問題/健檢：進度查詢`
- 分隔符：category 與 topic 間用 `/`，路徑與 question 間用全形 `：`

### 關鍵陷阱（務必正確處理）
category 下拉可停在「全部科別」（`ALL_CATEGORIES_VALUE`），**不能拿畫面篩選值當前綴**。
且 `QaTopic` 型別**不帶 `categoryId`**（只有 id/order/label/questions）——category↔topic
歸屬靠 `QaCategory.topics[]` 包含關係表達。因此前綴的 category 必須從 topic **反查**：

```ts
const owningCategory = categories.find(c => c.topics.some(t => t.id === selectedTopic.id));
```

即使下拉停在「全部」，也抓到 question 真正所屬的 category。

### 降級規則
1. 有 category + topic → `分類/主題：question`
2. 無 category（categories 空或反查不到）→ `主題：question`
3. 無 topic → 純 `question`

```ts
const prefix = [owningCategory?.label, selectedTopic.label].filter(Boolean).join('/');
const text = prefix ? `${prefix}：${question}` : question;
onSelectQuestion(text);
```

### 範圍
前綴邏輯放**共用元件 `QaTopicGrid.tsx`**，hciot 與 general **都套用**（兩者都用此元件）。

### 影響面
`onSelectQuestion` 的呼叫端（`pages/Hciot.tsx:1028`、`pages/General.tsx:138`、
`components/general/SuggestSidebar.tsx`）收到的字串變長（含前綴），但介面型別不變
（仍是 `(question: string) => void`），呼叫端無需改。

## 功能 2：回答圖片點擊原地放大（lightbox），不開新分頁

### 現況
`src/components/hciot/HciotImageAttachment.tsx` 用 `<a href target="_blank">`（L17-23）
包圖片 → 點擊開新分頁。

### 目標
點圖片改成**原地放大顯示**（全螢幕遮罩 lightbox），不開新分頁。

### 做法（複用現成元件）
專案已有 `src/components/_shared/qaKnowledgeWorkspace/ImageLightbox.tsx`（介面
`{ url, alt, onClose }`，已含 ESC 關閉、點背景關閉、關閉按鈕）——**直接複用，不自造**。

改 `HciotImageAttachment.tsx`：
1. 加 `const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)`
2. `<a href target="_blank">` → `<button>`（點擊 `setLightboxUrl(imageUrl)`），保留 `<img>` 預覽
3. 渲染 `<ImageLightbox url={lightboxUrl} alt={...} onClose={() => setLightboxUrl(null)} />`
4. lightbox state 放元件內部（選項 A，每張圖自管；無翻圖需求，YAGNI）

### 必要的 CSS 補載（否則 lightbox 無樣式）
lightbox 樣式定義在 `src/styles/qaWorkspace/workspace-images.css`，但
`pages/Hciot.tsx` 目前**漏 import 這份**（有 import workspace.css/workspace-upload.css 等）。
需在 `Hciot.tsx` 補一行：

```ts
import '../styles/qaWorkspace/workspace-images.css';
```

## 改動清單總覽

| 檔案 | 功能 | 改動 |
|---|---|---|
| `src/components/_shared/QaTopicGrid.tsx` | 1 | question 點擊送出帶路徑前綴（從 topic 反查 category） |
| `src/components/hciot/HciotImageAttachment.tsx` | 2 | `<a target=_blank>` → `<button>` + lightbox state，複用 ImageLightbox |
| `src/pages/Hciot.tsx` | 2 | 補 import `workspace-images.css` |

## 不在範圍
- 後端不動。
- 不做圖片翻頁（上一張/下一張）——無需求，YAGNI。
- 不改 `onSelectQuestion` 等介面型別。

## 驗收
- 功能 1：hciot 與 general 點 question，送出文字含正確前綴；category 下拉停「全部」時仍抓到正確分類；無 category 時降級正常。
- 功能 2：hciot 回答圖片點擊原地放大、ESC/點背景/關閉鈕可關、不再開新分頁、樣式正常。
- 遵守前端慣例：相對單位（rem/%/vh），不新增 px。
