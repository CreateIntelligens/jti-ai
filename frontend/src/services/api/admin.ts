import { API_BASE, fetchAsAdmin, handleResponse } from './base';

export type DbSyncApp = 'jti' | 'hciot' | 'general';
export type DbSyncDirection = 'forward' | 'reverse';

export interface DbSyncResult {
  ok: boolean;
  app: string;
  direction: DbSyncDirection;
  dry_run: boolean;
  databases: Record<string, Record<string, Record<string, number | string>>>;
  elapsed_sec: number;
  // forward（主庫 → 備援庫）：total_upserted=新增；total_modified=實際更新（值真的改）；
  // total_matched=比對到的總數（含值沒變的，不代表有更新）。
  total_upserted: number;
  total_modified: number;
  total_matched: number;
  // reverse：補入/略過（備援庫 → 主庫，AWS 為主只補不覆蓋）。
  total_inserted: number;
  total_skipped: number;
}

/**
 * 觸發資料庫同步（super_admin only）。走 cookie session 身份（fetchAsAdmin）。
 * - direction='forward'（預設）：DocumentDB → Atlas（平時備份）。
 * - direction='reverse'：Atlas → DocumentDB（災後補回主庫，AWS 為主只補不覆蓋）。
 * - app='jti'/'hciot'：只同步該應用；app='general'：全域（所有應用 + 系統設定）。
 * - dryRun=true：只預演統計、不寫入。
 */
export async function triggerDbSync(
  app: DbSyncApp,
  options: { direction?: DbSyncDirection; dryRun?: boolean } = {},
): Promise<DbSyncResult> {
  const { direction = 'forward', dryRun = false } = options;
  const response = await fetchAsAdmin(`${API_BASE}/admin/db-sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app, direction, dry_run: dryRun }),
  });
  return handleResponse<DbSyncResult>(response);
}
