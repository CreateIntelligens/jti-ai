"""
Gemini File Search CLI 互動介面
"""

import sys
from .core import FileSearchManager


def print_menu():
    """顯示主選單。"""
    print("\n=== Gemini File Search CLI ===")
    print("1. 列出所有 Store")
    print("2. 建立新 Store")
    print("3. 上傳檔案")
    print("4. 查詢")
    print("5. 列出 Store 中的檔案")
    print("6. 刪除 Store")
    print("0. 離開")
    print("=" * 30)


def main():
    """CLI 主程式。"""
    try:
        manager = FileSearchManager()
    except ValueError as e:
        print(f"錯誤: {e}")
        sys.exit(1)

    current_store: str | None = None

    while True:
        print_menu()
        if current_store:
            print(f"[目前 Store: {current_store}]")

        choice = input("\n請選擇 (0-6): ").strip()

        if choice == "0":
            print("再見！")
            break

        elif choice == "1":
            stores = manager.list_stores()
            if stores:
                print("\n現有 Stores:")
                for i, store in enumerate(stores, 1):
                    print(f"  {i}. {store.name}")
                    print(f"     顯示名稱: {store.display_name}")
            else:
                print("\n(無任何 Store)")

        elif choice == "2":
            name = input("輸入 Store 顯示名稱: ").strip()
            if name:
                current_store = manager.create_store(name)

        elif choice == "3":
            if not current_store:
                store_name = input("輸入 Store 名稱 (或按 Enter 先列出): ").strip()
                if not store_name:
                    stores = manager.list_stores()
                    for s in stores:
                        print(f"  - {s.name}")
                    store_name = input("輸入 Store 名稱: ").strip()
                current_store = store_name

            file_path = input("輸入檔案路徑: ").strip()
            if file_path:
                try:
                    manager.upload_file(current_store, file_path)
                except Exception as e:
                    print(f"上傳失敗: {e}")

        elif choice == "4":
            if not current_store:
                store_name = input("輸入 Store 名稱: ").strip()
                current_store = store_name

            question = input("輸入問題: ").strip()
            if question:
                try:
                    response = manager.query(current_store, question)
                    print("\n--- 回答 ---")
                    print(response.text)
                except Exception as e:
                    print(f"查詢失敗: {e}")

        elif choice == "5":
            if not current_store:
                store_name = input("輸入 Store 名稱: ").strip()
                current_store = store_name

            try:
                files = manager.list_files(current_store)
                if files:
                    print("\n檔案列表:")
                    for f in files:
                        print(f"  - {f.name}")
                else:
                    print("\n(無檔案)")
            except Exception as e:
                print(f"列出失敗: {e}")

        elif choice == "6":
            store_name = input("輸入要刪除的 Store 名稱: ").strip()
            if store_name:
                confirm = input(f"確定刪除 {store_name}? (y/N): ").strip().lower()
                if confirm == "y":
                    try:
                        manager.delete_store(store_name)
                        if current_store == store_name:
                            current_store = None
                    except Exception as e:
                        print(f"刪除失敗: {e}")

        else:
            print("無效選項")


if __name__ == "__main__":
    main()
