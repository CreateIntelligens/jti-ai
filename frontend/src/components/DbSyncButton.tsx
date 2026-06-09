import { useState } from 'react';
import { RefreshCw, Loader } from 'lucide-react';
import { triggerDbSync, type DbSyncApp } from '../services/api';
import { toErrorMessage } from '../utils/errors';

interface DbSyncButtonProps {
  /** 同步範圍：'jti'/'hciot' 只同步該應用；'general' 為全域同步。 */
  app: DbSyncApp;
  /** 套用既有的 icon button 樣式（各頁傳入對應 class）。 */
  className?: string;
}

const CONFIRM_TEXT: Record<DbSyncApp, string> = {
  jti: '確定要將「JTI」資料同步至備援庫嗎？',
  hciot: '確定要將「HCIoT」資料同步至備援庫嗎？',
  general: '確定要執行「全域同步」嗎？這會同步所有應用資料與系統設定至備援庫。',
};

const TITLE_TEXT: Record<DbSyncApp, string> = {
  jti: '同步本應用資料至備援庫',
  hciot: '同步本應用資料至備援庫',
  general: '全域同步（所有應用 + 系統設定）至備援庫',
};

/**
 * DocumentDB → Atlas 同步按鈕（super_admin only）。
 * 呼叫端負責只在 super_admin 時 render 本元件。
 */
export default function DbSyncButton({ app, className }: DbSyncButtonProps) {
  const [syncing, setSyncing] = useState(false);

  const handleClick = async () => {
    if (syncing) return;
    if (!window.confirm(CONFIRM_TEXT[app])) return;

    setSyncing(true);
    try {
      const result = await triggerDbSync(app);
      const dbCount = Object.keys(result.databases).length;
      window.alert(
        `同步完成（${dbCount} 個資料庫）\n` +
          `新增 ${result.total_upserted}、實際更新 ${result.total_modified}，` +
          `耗時 ${result.elapsed_sec}s`,
      );
      // 註：此鈕固定 forward（主庫 → 備援庫）。反向補回主庫在後台 General 設定選單。
    } catch (e) {
      window.alert(`同步失敗：${toErrorMessage(e)}`);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <button
      type="button"
      className={className}
      onClick={() => void handleClick()}
      disabled={syncing}
      title={syncing ? '同步進行中…' : TITLE_TEXT[app]}
      aria-busy={syncing}
    >
      {syncing ? <Loader size={18} className="db-sync-spin" /> : <RefreshCw size={18} />}
    </button>
  );
}
