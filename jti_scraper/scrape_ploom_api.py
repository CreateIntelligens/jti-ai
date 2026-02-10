"""
Ploom 商品 API 爬蟲

直接呼叫 GraphQL API 取得商品資訊，不需要瀏覽器
"""

import requests
import json
import re
import os
from pathlib import Path
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── 結構化規格資料 ──────────────────────────────────────────
# 由於 API 不提供結構化規格，這裡手動補充

PRODUCT_SPECS = {
    "Ploom X 菸草加熱器": {
        "電池類型電池容量": "鋰離子電池 2,800 mAh",
        "尺寸": "大約 43.5 mm 寬 x 88.5 mm 高 x 24.0 mm",
        "輸入端子": "USB (C)",
        "充電時間（Ploom 電源供應器）": "大約 110 分鐘，至少可用 20 根菸彈",
        "額定電壓 / 額定電流": "5 V ⎓ / 1.5 A",
        "Stick compatibility": "七星"
    },
    "充電底座": {
        "尺寸": "5.68 (L) x 4.71 (W) x 1.8 (H) cm，傳輸線長 75 cm",
        "重量": "92.5 g",
        "材質": "鋁、矽氧樹脂",
        "額定電壓 / 額定電流": "5 V ⎓ / 1.5 A",
        "充電時間": "大約 110 分鐘"
    },
    "前保護殼": {
        "尺寸": "8.44 (L) x 4.09 (W) x 0.58 (H) cm",
        "重量": "4.3 g",
        "材質": "聚碳酸酯樹脂"
    },
    "後保護殼": {
        "尺寸": "8.5 (L) x 4.75 (W) x 2.22 (H) cm",
        "重量": "1.25 g",
        "材質": "織布、再生聚酯"
    },
    "隨身收納盒": {
        "尺寸": "15.3 (L) x 7.5 (W) x 2.9 (H) cm",
        "重量": "53 g",
        "材質": "皮革、再生聚酯"
    }
}


# ── 商品歸類規則 ──────────────────────────────────────────

PRODUCT_RULES = [
    (lambda n: "前保護殼" in n, "前保護殼", "配件"),
    (lambda n: "後保護殼" in n, "後保護殼", "配件"),
    (lambda n: "Front Panel" in n, "前保護殼", "配件"),
    (lambda n: "隨身收納盒" in n, "隨身收納盒", "配件"),
    (lambda n: "All-In-One Carry Case" in n, "隨身收納盒", "配件"),
    (lambda n: "Fabric Carry Case" in n, "織布收納包", "配件"),
    (lambda n: "清潔棒" in n or "Cleaning Sticks" in n, "清潔棒", "配件"),
    (lambda n: "充電底座" in n, "充電底座", "配件"),
    (lambda n: "USB" in n or "傳輸線" in n or "Wall Adaptor" in n, "充電器 / 傳輸線", "配件"),
    (lambda n: "Car Holder" in n, "車用支架", "配件"),
    (lambda n: "Stick Tray" in n, "菸彈收納盒", "配件"),
    (lambda n: "Starter Bundle" in n, "Ploom X 入門套組", "加熱器"),
    (lambda n: "加熱器" in n or "菸草加熱器" in n, "Ploom X 菸草加熱器", "加熱器"),
    (lambda n: re.search(r"Ploom\s*X", n), "Ploom X 菸草加熱器", "加熱器"),
]


def classify_product(name: str) -> tuple[str, str]:
    """回傳 (商品名稱, 分類)"""
    for match_fn, product_name, category in PRODUCT_RULES:
        if match_fn(name):
            return product_name, category
    return name, "其他"


def extract_color(name: str) -> str:
    """從商品名稱提取顏色 / 款式"""
    m = re.search(r'–\s*(.+)$', name)
    if m:
        return m.group(1).strip()

    m = re.search(r'(?:前保護殼|後保護殼|隨身收納盒)\s+(.+)', name)
    if m:
        return m.group(1).strip()

    m = re.search(r'-\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)(?:\s*-\s*.*)?$', name)
    if m:
        candidate = m.group(1).strip()
        if candidate not in ("EM Test", "Ito"):
            return candidate

    return ""


def clean_html(html: str) -> str:
    # 把 <br> <p> 換成換行，再移除其他標籤
    text = re.sub(r'<br\s*/?>', '\n', html)
    text = re.sub(r'</p>\s*<p>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\r\n', '\n', text)
    # 每行 trim，移除空行
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join(line for line in lines if line)


def scrape_ploom_products_api(output_file: str = "ploom_products.json"):
    """透過 GraphQL API 抓取 Ploom 商品"""

    api_url = "https://api.jtides.com/des-ecommerce/m24-ploom-tw/v1/graphql"

    query = """
    query GetProducts {
        products(
            search: ""
            filter: {}
            pageSize: 1000
            currentPage: 1
        ) {
            items {
                name
                url_key
                image { url }
                short_description { html }
                description { html }
                categories { name }
            }
            total_count
        }
    }
    """

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        logger.info("正在呼叫 GraphQL API...")
        response = requests.post(api_url, json={"query": query}, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        logger.info(f"API 回應狀態: {response.status_code}")

        if "data" not in data or "products" not in data["data"]:
            if "errors" in data:
                logger.error(f"GraphQL 錯誤: {data['errors']}")
            else:
                logger.warning(f"未預期的回應格式: {data}")
            return None

        items = data["data"]["products"].get("items", [])
        logger.info(f"成功取得 {len(items)} 個商品")

        # ── 整理每筆 item ──
        all_items = []
        for item in items:
            name = re.sub(r'\s+', ' ', item.get("name", "")).strip()
            product_name, category = classify_product(name)
            color = extract_color(name)

            all_items.append({
                "name": name,
                "product_name": product_name,
                "category": category,
                "color": color,
                "url": f"https://www.ploom.tw/zh/{item.get('url_key', '')}.html",
                "image": item.get("image", {}).get("url"),
                "short_description": clean_html(
                    (item.get("short_description") or {}).get("html", "")
                ),
                "description": clean_html(
                    (item.get("description") or {}).get("html", "")
                ),
            })

        # ── 按商品整合 ──
        products_map = defaultdict(lambda: {
            "product_name": "",
            "category": "",
            "summary": "",
            "features": "",
            "specs": {},
            "variants": [],
        })

        for it in all_items:
            key = it["product_name"]
            entry = products_map[key]
            entry["product_name"] = it["product_name"]
            entry["category"] = it["category"]
            if not entry["summary"] and it["short_description"]:
                entry["summary"] = it["short_description"]
            if not entry["features"] and it["description"]:
                entry["features"] = it["description"]

            # 加入結構化規格
            if not entry["specs"] and key in PRODUCT_SPECS:
                entry["specs"] = PRODUCT_SPECS[key]

            entry["variants"].append({
                "color": it["color"] or it["name"],
                "name": it["name"],
                "url": it["url"],
                "image": it["image"],
            })

        # 轉成 list 並排序
        products = sorted(products_map.values(), key=lambda p: p["category"])

        # ── 去重 variants ──
        for p in products:
            seen = set()
            unique = []
            for v in p["variants"]:
                if v["name"] in seen:
                    continue
                seen.add(v["name"])
                unique.append(v)
            p["variants"] = unique

        # ── 儲存 JSON ──
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        logger.info(f"商品資訊已儲存至: {output_path}")

        # ── 印出統計 ──
        logger.info(f"\n=== 商品統計：{len(products)} 個商品 ===")
        for p in products:
            n_variants = len(p["variants"])
            logger.info(f"  [{p['category']}] {p['product_name']}  ({n_variants} 款)")

        return products

    except requests.exceptions.RequestException as e:
        logger.error(f"API 請求失敗: {e}")
        return None
    except Exception as e:
        logger.error(f"發生錯誤: {e}")
        return None


def generate_products_md(products: list, output_file: str) -> None:
    """生成商品 Markdown，按商品整合顏色"""
    lines = ["# Ploom 商品目錄", ""]

    by_category = defaultdict(list)
    for p in products:
        by_category[p["category"]].append(p)

    cat_order = ["加熱器", "配件", "其他"]
    sorted_cats = sorted(by_category.keys(), key=lambda c: cat_order.index(c) if c in cat_order else 999)

    for cat in sorted_cats:
        lines.append(f"## {cat}")
        lines.append("")

        for p in by_category[cat]:
            lines.append(f"### {p['product_name']}")
            lines.append("")

            if p["summary"]:
                lines.append(p["summary"])
                lines.append("")

            if p.get("features"):
                lines.append(f"**產品特色：** {p['features']}")
                lines.append("")

            # 結構化規格表
            if p.get("specs"):
                lines.append("**規格：**")
                lines.append("")
                for spec_key, spec_value in p["specs"].items():
                    lines.append(f"- **{spec_key}**: {spec_value}")
                lines.append("")

            lines.append("可選款式：")
            for v in p["variants"]:
                color_display = v["color"] if v["color"] else v["name"]
                lines.append(f"- {color_display}")

            lines.append("")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"商品 Markdown 已生成: {output_path}")


def main():
    """主函數"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    output_json = os.path.join(project_dir, ".claude", "ploom_products.json")
    output_md = os.path.join(project_dir, ".claude", "ploom_products.md")

    products = scrape_ploom_products_api(output_json)

    if products:
        print(f"\n✅ 完成！共整理出 {len(products)} 個商品")
        print(f"JSON: {output_json}")
        generate_products_md(products, output_md)
        print(f"Markdown: {output_md}")
    else:
        print("\n❌ 未能抓取到商品資料")


if __name__ == "__main__":
    main()
