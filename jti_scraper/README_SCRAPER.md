# Ploom 資料爬蟲

兩個腳本分別抓取 FAQ 問答和商品資訊，各自輸出 JSON + Markdown。

## 安裝

```bash
pip install requests
```

（FAQ 爬蟲不需要額外套件，使用 Python 標準庫）

---

## 1. 商品爬蟲 `scrape_ploom_api.py`

透過 GraphQL API 抓取商品資訊，不需要瀏覽器或登入。

```bash
python3 scripts/scrape_ploom_api.py
```

### 輸出

- `.claude/ploom_products.json` — 按商品整合的結構化資料
- `.claude/ploom_products.md` — 方便閱讀的 Markdown 商品目錄

### JSON 結構

商品會自動整合同一產品的不同顏色/款式（不含價格與庫存），並包含產品特色與結構化規格：

```json
[
  {
    "product_name": "Ploom X 菸草加熱器",
    "category": "加熱器",
    "summary": "Ploom X 是豐富風味...",
    "features": "Ploom X 使用「HeatFlow™ 熱對流菸草加熱科技」...",
    "specs": {
      "電池類型電池容量": "鋰離子電池 2,800 mAh",
      "尺寸": "大約 43.5 mm 寬 x 88.5 mm 高 x 24.0 mm",
      "輸入端子": "USB (C)",
      "充電時間（Ploom 電源供應器）": "大約 110 分鐘，至少可用 20 根菸彈",
      "額定電壓 / 額定電流": "5 V ⎓ / 1.5 A",
      "Stick compatibility": "七星"
    },
    "variants": [
      {
        "color": "金",
        "name": "Ploom X 菸草加熱器 – 金",
        "url": "https://www.ploom.tw/zh/ploom-gold.html",
        "image": "https://m24-ploom-tw.jtides.com/media/..."
      }
    ]
  }
]
```

**欄位說明：**
- `summary` - 商品簡介（來自 API 的 short_description）
- `features` - 產品特色與功能描述（來自 API 的 description）
- `specs` - 結構化技術規格（手動補充，目前包含 Ploom X 菸草加熱器、充電底座、前保護殼、後保護殼、隨身收納盒）

### 商品分類

| 分類 | 商品 |
|------|------|
| 加熱器 | Ploom X 菸草加熱器、入門套組 |
| 配件 | 前保護殼、後保護殼、隨身收納盒、織布收納包、菸彈收納盒、充電底座、充電器/傳輸線、車用支架、清潔棒 |

---

## 2. FAQ 爬蟲 `ploom_faq_scraper.py`

從 Ploom 支援頁面抓取常見問題與解答，支援多執行緒並行。

```bash
python3 scripts/ploom_faq_scraper.py
```

### 輸出

- `.claude/ploom_faq.json` — 含分類的 FAQ 資料
- `.claude/ploom_faq.md` — 按分類整理的 Markdown

### FAQ 分類

關於 Ploom、裝置保養、菸彈、配件、訂單配送、年齡驗證、帳戶註冊、裝置註冊、裝置保固與更換、Ploom Care 團隊

### 可選參數

```bash
python3 scripts/ploom_faq_scraper.py --workers 8 --timeout 20 --retries 3
```

---

## 測試結果

- 商品：64 個 SKU → 整合為 11 個商品（2026-02-10）
- FAQ：61 筆問答，10 個分類（2026-02-10）
