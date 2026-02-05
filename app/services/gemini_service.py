"""
Gemini API 整合服務（使用新版 google-genai SDK）

職責：
1. 上傳知識庫檔案（docx）到 Gemini File API
2. 建立 File Search Store
3. 提供 Main Agent 呼叫介面
"""

import os
import google.genai as genai
from google.genai import types
from pathlib import Path
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

# 設定 API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found in environment")

# 新版 SDK 使用 Client
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


class GeminiService:
    """Gemini 服務封裝"""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.file_search_store_id: Optional[str] = None
        self.client = client

    async def upload_knowledge_base(
        self, file_path: str, display_name: str = "Color Quiz Knowledge Base"
    ) -> str:
        """
        上傳知識庫檔案到 Gemini

        Args:
            file_path: 檔案路徑（docx）
            display_name: 顯示名稱

        Returns:
            file_name: Gemini File name
        """
        try:
            if not self.client:
                raise ValueError("Gemini client not initialized")

            logger.info(f"Uploading file: {file_path}")

            # 上傳檔案
            uploaded_file = self.client.files.upload(path=file_path)

            logger.info(f"Uploaded file: {uploaded_file.name}")
            return uploaded_file.name

        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise

    def get_model_with_tools(
        self, tools: List[Dict], store_id: Optional[str] = None
    ) -> str:
        """
        取得 Model 名稱（供 generate_content 使用）

        Args:
            tools: Custom function tools
            store_id: File Search Store ID

        Returns:
            model_name: 模型名稱
        """
        # 新版 SDK 中，tools 在 generate_content 時才傳入
        return self.model_name


# 全域實例
gemini_service = GeminiService()


# === 初始化：上傳知識庫 ===

async def initialize_knowledge_base():
    """
    初始化知識庫

    上傳 docx 檔案
    這個函數應該在服務啟動時呼叫一次
    """
    kb_file = "傑太日煙＿FAQ_draft_for 創智.docx"

    if not Path(kb_file).exists():
        logger.warning(f"Knowledge base file not found: {kb_file}")
        return None

    try:
        # 上傳檔案
        file_name = await gemini_service.upload_knowledge_base(
            file_path=kb_file,
            display_name="傑太日煙 FAQ"
        )

        logger.info(f"Knowledge base initialized: {file_name}")
        return file_name

    except Exception as e:
        logger.error(f"Failed to initialize knowledge base: {e}")
        return None
