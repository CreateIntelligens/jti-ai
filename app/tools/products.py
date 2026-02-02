"""
商品推薦工具

職責：
1. 根據 persona 過濾商品
2. 回傳結構化商品清單
3. LLM 僅能根據 tool 結果生成文案
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# 載入商品資料庫
PRODUCTS_PATH = Path("data/products.json")
products_data = None


def load_products():
    """載入商品資料庫"""
    global products_data
    if products_data is None:
        with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
            products_data = json.load(f)
    return products_data


def recommend_products(
    persona: str,
    filters: Optional[Dict] = None,
    max_results: int = 3
) -> List[Dict]:
    """
    推薦商品

    Args:
        persona: MBTI 類型，例如 "INTJ"
        filters: 額外過濾條件，例如 {"age": "20+", "region": "TW"}
        max_results: 最多回傳幾個商品

    Returns:
        [
            {
                "sku": str,
                "name": str,
                "price": int,
                "description": str,
                "tags": list,
                ...
            }
        ]
    """
    try:
        products_db = load_products()
        all_products = products_db["products"]

        # 1. 過濾：persona_fit 包含該 MBTI 類型
        matched_products = [
            p for p in all_products
            if persona in p.get("persona_fit", [])
        ]

        # 2. 額外過濾條件（可選）
        if filters:
            matched_products = _apply_filters(matched_products, filters)

        # 3. 排序：根據 style_vector 與 persona 的匹配度（可擴充）
        # 目前先簡單回傳前 N 個
        matched_products = matched_products[:max_results]

        logger.info(
            f"Recommended {len(matched_products)} products for {persona}"
        )
        return matched_products

    except Exception as e:
        logger.error(f"Failed to recommend products: {e}")
        return []


def _apply_filters(products: List[Dict], filters: Dict) -> List[Dict]:
    """套用額外過濾條件"""
    filtered = products

    # 年齡過濾
    if "age" in filters:
        # 簡化：目前不實作複雜的年齡比對
        pass

    # 地區過濾
    if "region" in filters:
        region = filters["region"]
        filtered = [
            p for p in filtered
            if region in p.get("constraints", {}).get("region", [])
        ]

    return filtered


def get_product_by_sku(sku: str) -> Optional[Dict]:
    """根據 SKU 取得商品"""
    try:
        products_db = load_products()
        for product in products_db["products"]:
            if product["sku"] == sku:
                return product
        return None
    except Exception as e:
        logger.error(f"Failed to get product: {e}")
        return None


def search_products_by_tag(tag: str, max_results: int = 5) -> List[Dict]:
    """根據標籤搜尋商品"""
    try:
        products_db = load_products()
        all_products = products_db["products"]

        matched = [
            p for p in all_products
            if tag in p.get("tags", [])
        ]

        return matched[:max_results]

    except Exception as e:
        logger.error(f"Failed to search products: {e}")
        return []
