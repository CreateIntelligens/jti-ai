"""
Gemini File Search API 範例程式

此模組示範如何使用 Google Gemini 的 File Search API
建立知識庫並進行語義查詢。
"""

import mimetypes
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


def log(message: str) -> None:
    """輸出帶有時間戳的日誌訊息。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


class FileSearchManager:
    """Gemini File Search API 封裝類別。

    Attributes:
        client: GenAI Client 實例
        store_name: 目前使用的 File Search Store 資源名稱
    """

    def __init__(self, api_key: str | None = None):
        """初始化 FileSearchManager。

        Args:
            api_key: Gemini API Key（若未提供則從環境變數讀取）
        """
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("未設定 GEMINI_API_KEY")

        self.client = genai.Client(api_key=api_key)
        self.store_name: str | None = None

    def create_store(self, display_name: str) -> str:
        """建立新的 File Search Store。

        Args:
            display_name: Store 顯示名稱

        Returns:
            Store 資源名稱
        """
        store = self.client.file_search_stores.create(
            config={"display_name": display_name}
        )
        self.store_name = store.name
        log(f"已建立 Store: {self.store_name}")
        return self.store_name

    def list_stores(self) -> list:
        """列出所有 File Search Store。

        Returns:
            Store 列表
        """
        stores = self.client.file_search_stores.list()
        return list(stores)

    def get_store(self, store_name: str):
        """取得指定 Store。

        Args:
            store_name: Store 資源名稱

        Returns:
            Store 物件
        """
        return self.client.file_search_stores.get(name=store_name)

    def delete_store(self, store_name: str) -> None:
        """刪除指定 Store (會先清空其中的檔案)。

        Args:
            store_name: Store 資源名稱
        """
        # 1. 先列出並刪除所有檔案
        try:
            files = self.list_files(store_name)
            for f in files:
                try:
                    self.delete_file(f.name)
                except Exception as e:
                    log(f"刪除檔案失敗 {f.name}: {e}")
        except Exception as e:
            log(f"列出檔案失敗 (可能 Store 已不存在): {e}")

        # 2. 刪除 Store 本身
        self.client.file_search_stores.delete(name=store_name)
        log(f"已刪除 Store: {store_name}")

    def upload_file(
        self,
        store_name: str,
        file_path: str,
        display_name: str | None = None,
        mime_type: str | None = None,
        poll_interval: float = 5.0,
    ) -> str:
        """上傳檔案到 Store。

        Args:
            store_name: Store 資源名稱
            file_path: 檔案路徑
            display_name: 檔案顯示名稱（選填）
            mime_type: MIME 類型（選填，自動偵測）
            poll_interval: 輪詢間隔秒數

        Returns:
            上傳的檔案資源名稱
        """
        display_name = display_name or Path(file_path).name

        # 優先根據副檔名判定 MIME Type，確保相容性
        # 注意：file_path 可能是暫存檔 (無副檔名)，所以要用 display_name
        ext = Path(display_name).suffix.lower()
        
        known_types = {
            # --- 僅保留驗證過可行的二進位格式 ---
            # Office 格式 (docx, xlsx 等) 因 MIME 字串過長或 API 驗證問題，
            # 必須留空 (None) 讓 API 自動偵測，否則會報 400 錯誤。
            
            # PDF (驗證 OK)
            ".pdf": "application/pdf",
            
            # 壓縮檔 (驗證 OK，雖然測試檔要是真的 zip)
            ".zip": "application/zip",
        }

        # 優先使用對照表
        if ext in known_types:
            mime_type = known_types[ext]
        else:
            # 對於不在 known_types 裡的檔案 (Office, Code, Text...)
            # 我們強制設為 "text/plain" 以確保能成功上傳。
            # 目前 Gemini API 對於 Office 檔案的標準 MIME Type 驗證極嚴格 (會報 400)，
            # 且 SDK 不支援 mime_type=None。
            # 雖然 text/plain 對二進位檔不是最佳解，但至少能保證不報錯。
            if not mime_type:
                mime_type = "text/plain"

        log(f"上傳中: {display_name} (mime={mime_type})")

        operation = self.client.file_search_stores.upload_to_file_search_store(
            file=file_path,
            file_search_store_name=store_name,
            config={"display_name": display_name, "mime_type": mime_type},
        )
        while not operation.done:
            time.sleep(poll_interval)
            operation = self.client.operations.get(operation)

        log(f"已上傳: {display_name}")
        if operation.response:
            return operation.response.document_name
        return ""

    def delete_file(self, file_name: str) -> None:
        """刪除指定檔案。

        Args:
            file_name: 檔案資源名稱 (documents/...)
        """
        self.client.file_search_stores.documents.delete(
            name=file_name,
            config={"force": True}
        )
        log(f"已刪除檔案: {file_name}")

    def list_files(self, store_name: str) -> list:
        """列出 Store 中的所有檔案。

        Args:
            store_name: Store 資源名稱

        Returns:
            檔案列表 (包含 name, display_name)
        """
        files = self.client.file_search_stores.documents.list(
            parent=store_name
        )
        return list(files)

    @staticmethod
    def _build_history_contents(chat_history: list) -> list:
        """將 MongoDB 格式的 chat_history 轉換為 Gemini SDK Content 物件"""
        contents = []
        for msg in chat_history:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["content"])]
                )
            )
        return contents

    def start_chat(self, store_name: str, model: str = "gemini-2.5-flash",
                   system_instruction: str = None, history: list = None):
        """開始一個新的 Chat Session (多輪對話)。

        Args:
            store_name: Store 資源名稱
            model: 使用的模型名稱
            system_instruction: 系統指令
            history: 既有的對話歷史 Content 物件列表（用於從 MongoDB 恢復）
        """
        if system_instruction:
            log(f"[Core] 設定 system_instruction: {system_instruction[:50]}...")
        else:
            log("[Core] 沒有 system_instruction")

        # 封裝為 SDK 偏好的格式
        si = None
        if system_instruction:
            si = [types.Part.from_text(text=system_instruction)]

        # 保存 Config 供後續 send_message 使用
        self.current_config = types.GenerateContentConfig(
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store_name]
                    )
                )
            ],
            system_instruction=si
        )

        self.chat_session = self.client.chats.create(
            model=model,
            config=self.current_config,
            history=history or []
        )
        self.current_store = store_name
        return self.chat_session

    def send_message(self, message: str):
        """發送訊息到目前的 Chat Session。"""
        if not hasattr(self, 'chat_session') or not self.chat_session:
            raise ValueError("請先選擇 Store 以開始對話")

        # 確保在發送訊息時也帶上 config
        response = self.chat_session.send_message(
            message=message,
            config=self.current_config
        )
        return response

    def get_history(self):
        """取得對話歷史紀錄。"""
        if not hasattr(self, 'chat_session') or not self.chat_session:
            return []
        
        # 使用 _curated_history，因為 history 屬性不存在
        # 注意：這依賴於 SDK 的內部實作，未來版本可能會變
        raw_history = getattr(self.chat_session, '_curated_history', [])
        
        history = []
        for content in raw_history:
            role = content.role # 'user' or 'model'
            # 簡單處理：只取第一個 part 的 text
            text = ""
            if content.parts:
                for part in content.parts:
                    if part.text:
                        text += part.text
            history.append({"role": role, "text": text})
        return history

    def query(
        self,
        store_name: str,
        question: str,
        model: str = "gemini-2.5-flash",
        system_instruction: str | None = None,
    ) -> types.GenerateContentResponse:
        """使用 File Search 查詢。

        Args:
            store_name: Store 資源名稱
            question: 問題
            model: 使用的模型名稱
            system_instruction: 系統指令（選填）

        Returns:
            GenerateContentResponse 物件
        """
        # 建立 config
        si = None
        if system_instruction:
            si = [types.Part.from_text(text=system_instruction)]

        response = self.client.models.generate_content(
            model=model,
            contents=question,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[store_name]
                        )
                    )
                ],
                system_instruction=si
            ),
        )
        return response


def main():
    """主程式進入點。"""
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        log("錯誤：未設定 GEMINI_API_KEY")
        log("請複製 .env.example 為 .env 並填入 API Key")
        return

    manager = FileSearchManager(api_key)

    print("=== Gemini File Search API 範例 ===\n")

    # 列出現有 Store
    print("現有 File Search Stores:")
    stores = manager.list_stores()
    for store in stores:
        print(f"  - {store.name} ({store.display_name})")

    if not stores:
        print("  (無)")

    print("\n--- 使用範例 ---")
    print("1. manager.create_store('我的知識庫')")
    print("2. manager.upload_file(store_name, 'document.pdf')")
    print("3. manager.query(store_name, '你的問題')")
    print("4. manager.list_files(store_name)")
    print("5. manager.delete_store(store_name)")


if __name__ == "__main__":
    main()