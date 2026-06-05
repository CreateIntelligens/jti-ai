"""集中管理 MongoDB database 名稱。

數據面（Data Plane）各應用獨立庫，避免跨 app 寄生在同一個 database。
歷史上 general 的 session / conversation 曾寄生於 ``jti_app``，已拆出獨立的
``general_app``（見 docs/superpowers/specs 的 MongoDB schema 審計文件）。

集中於此一處定義，讓 factory、stores、logger 等共用，避免散落的字面字串
造成歸屬不一致。
"""

# 數據面：各應用專屬資料庫
JTI_DB_NAME = "jti_app"
HCIOT_DB_NAME = "hciot_app"
GENERAL_DB_NAME = "general_app"

# 控制面：全系統管理資料庫（登入帳號、提示詞、金鑰、知識庫註冊表）。
# 早期遺留名 gemini_notebook 已遷移至語意正確的 system_config（見 schema 審計文件 §2.5）。
LEGACY_CONTROL_PLANE_DB_NAME = "gemini_notebook"
CONTROL_PLANE_DB_NAME = "system_config"
