"""DocumentDB → Atlas 同步 REST API(super_admin only)。

提供前端「同步」按鈕的後端入口。資料按 app 分 database(見
app/services/db_names.py),因此同步可限定範圍:

- jti    → jti_app
- hciot  → hciot_app
- general→ 全域:jti_app + hciot_app + general_app + system_config(控制面)

控制面(帳號/金鑰/提示詞/知識庫註冊表)只在 general 全域同步時帶,
單一 app 同步不碰控制面(職責清楚、避免重複同步)。

授權:僅 super_admin。整庫 upsert 是重量級 ops 動作,不開放一般 admin。
並發:module-level lock 確保同時只跑一個同步,避免重複觸發。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal

from app.auth import require_role
from app.services.db_names import (
    CONTROL_PLANE_DB_NAME,
    GENERAL_DB_NAME,
    HCIOT_DB_NAME,
    JTI_DB_NAME,
)
from app.services.db_sync.forward import (
    SyncConfigError,
    SyncConnectionError,
    run_forward_sync,
)
from app.services.db_sync.reverse import run_reverse_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["DB Sync"])

# 僅 super_admin。module-level 以便測試可用 dependency_overrides 覆寫。
require_super_admin_dep = require_role("super_admin")

# app → 要同步的 database 範圍。用 db_names 常數,不寫死字串。
_APP_DB_ALLOWLIST: dict[str, set[str]] = {
    "jti": {JTI_DB_NAME},
    "hciot": {HCIOT_DB_NAME},
    # general 視為全域入口:四個庫(含跨 app 共用的控制面)。
    "general": {JTI_DB_NAME, HCIOT_DB_NAME, GENERAL_DB_NAME, CONTROL_PLANE_DB_NAME},
}

# 確保同時只跑一個同步(整庫 upsert 不宜並發)。
_sync_lock = asyncio.Lock()


class DbSyncRequest(BaseModel):
    app: Literal["jti", "hciot", "general"]
    # forward = DocumentDB → Atlas(平時備份);reverse = Atlas → DocumentDB(災後補回)。
    direction: Literal["forward", "reverse"] = "forward"
    dry_run: bool = False


class DbSyncResponse(BaseModel):
    ok: bool
    app: str
    direction: str
    dry_run: bool
    databases: dict
    elapsed_sec: float
    # forward 用:total_upserted=新增;total_modified=實際更新(值真的改);
    # total_matched=比對到的總數(含值沒變的,⚠ 不代表有更新)。reverse 為 0。
    total_upserted: int = 0
    total_modified: int = 0
    total_matched: int = 0
    # reverse 用(補入/略過);forward 為 0。reverse 衝突時 AWS 主庫為準(只補不覆蓋)。
    total_inserted: int = 0
    total_skipped: int = 0


@router.post("/db-sync", response_model=DbSyncResponse)
async def trigger_db_sync(
    req: DbSyncRequest,
    auth: dict = Depends(require_super_admin_dep),
) -> DbSyncResponse:
    """觸發資料庫同步,方向(forward/reverse)與範圍(app)依請求決定。"""
    allowlist = _APP_DB_ALLOWLIST[req.app]

    if _sync_lock.locked():
        raise HTTPException(status_code=409, detail="同步進行中,請稍候再試")

    async with _sync_lock:
        actor = auth.get("user_id") or auth.get("role")
        logger.info(
            "[db-sync] 觸發者=%s app=%s direction=%s dry_run=%s 範圍=%s",
            actor, req.app, req.direction, req.dry_run, sorted(allowlist),
        )
        try:
            # pymongo 同步阻塞,丟到 executor 避免卡住 event loop。
            if req.direction == "reverse":
                # 反向預設 overwrite=False(AWS 為主,只補不覆蓋)。
                report = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: run_reverse_sync(db_allowlist=allowlist, dry_run=req.dry_run),
                )
            else:
                report = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: run_forward_sync(db_allowlist=allowlist, dry_run=req.dry_run),
                )
        except SyncConfigError as e:
            logger.error("[db-sync] 設定錯誤: %s", e)
            raise HTTPException(status_code=500, detail=f"同步設定錯誤: {e}") from e
        except SyncConnectionError as e:
            logger.error("[db-sync] 連線失敗: %s", e)
            raise HTTPException(status_code=502, detail=f"資料庫連線失敗: {e}") from e
        except Exception as e:  # noqa: BLE001 — 對外回 500,細節記 log
            logger.exception("[db-sync] 同步失敗")
            raise HTTPException(status_code=500, detail=f"同步失敗: {e}") from e

        logger.info(
            "[db-sync] 完成 app=%s direction=%s 耗時=%ss",
            req.app, req.direction, report["elapsed_sec"],
        )
        return DbSyncResponse(
            ok=True,
            app=req.app,
            direction=req.direction,
            dry_run=report["dry_run"],
            databases=report["databases"],
            elapsed_sec=report["elapsed_sec"],
            total_upserted=report.get("total_upserted", 0),
            total_modified=report.get("total_modified", 0),
            total_matched=report.get("total_matched", 0),
            total_inserted=report.get("total_inserted", 0),
            total_skipped=report.get("total_skipped", 0),
        )
