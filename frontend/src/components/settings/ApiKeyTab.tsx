import CustomSelect from '../CustomSelect';
import type { Store } from '../../types';

interface APIKey {
  id: string;
  key_prefix: string;
  name: string;
  store_name: string;
  prompt_index: number | null;
  created_at: string;
}

interface PromptItem {
  id: string;
  name: string;
  content: string;
  is_active: boolean;
}

export interface ApiKeyTabProps {
  stores: Store[];
  apiKeyStore: string;
  apiKeyName: string;
  apiKeyPromptIndex: string;
  apiKeyPrompts: PromptItem[];
  apiKeys: APIKey[];
  apiKeysLoading: boolean;
  apiKeyCreating: boolean;
  newApiKeyCreated: string | null;
  onApiKeyStoreChange: (v: string) => void;
  onApiKeyNameChange: (v: string) => void;
  onApiKeyPromptIndexChange: (v: string) => void;
  onCreateApiKey: () => void;
  onDeleteApiKey: (keyId: string) => void;
  onDismissNewKey: () => void;
}

export default function ApiKeyTab({
  stores,
  apiKeyStore,
  apiKeyName,
  apiKeyPromptIndex,
  apiKeyPrompts,
  apiKeys,
  apiKeysLoading,
  apiKeyCreating,
  newApiKeyCreated,
  onApiKeyStoreChange,
  onApiKeyNameChange,
  onApiKeyPromptIndexChange,
  onCreateApiKey,
  onDeleteApiKey,
  onDismissNewKey,
}: ApiKeyTabProps) {
  const getApiKeyPromptLabel = (promptIndex: number | null): string => {
    if (promptIndex == null) return '';
    if (apiKeyPrompts.length > 0 && promptIndex < apiKeyPrompts.length) {
      return apiKeyPrompts[promptIndex].name;
    }
    return `Prompt #${promptIndex}`;
  };

  return (
    <div className="modal-content">
      {newApiKeyCreated && (
        <div style={{
          padding: '1rem',
          background: 'var(--crystal-amber)',
          color: '#0a0f1a',
          borderRadius: '8px',
          marginBottom: '1rem'
        }}>
          <p style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>✓ API Key 已建立</p>
          <p style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>請妥善保存此金鑰，之後無法再次查看：</p>
          <code style={{
            display: 'block',
            padding: '0.5rem',
            background: 'rgba(0,0,0,0.2)',
            borderRadius: '4px',
            wordBreak: 'break-all'
          }}>
            {newApiKeyCreated}
          </code>
          <button
            onClick={onDismissNewKey}
            style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}
          >
            我已保存
          </button>
        </div>
      )}

      <div>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-blue)' }}>
          建立新的 API Key
        </h3>
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
            選擇知識庫
          </label>
          <CustomSelect
            value={apiKeyStore}
            onChange={onApiKeyStoreChange}
            options={[
              { value: "", label: "選擇知識庫..." },
              ...stores.map(store => ({
                value: store.name,
                label: store.display_name || store.name
              }))
            ]}
            className="w-full"
          />
        </div>
        {apiKeyStore && (
          <>
            {apiKeyPrompts.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
                  指定 Prompt（可選）
                </label>
                <CustomSelect
                  value={apiKeyPromptIndex}
                  onChange={onApiKeyPromptIndexChange}
                  options={[
                    { value: "", label: "使用預設（啟用中的 Prompt）" },
                    ...apiKeyPrompts.map((p, idx) => ({
                      value: String(idx),
                      label: `${p.name}${p.is_active ? ' (目前啟用)' : ''}`
                    }))
                  ]}
                  className="w-full"
                />
              </div>
            )}
            <div className="flex gap-md">
              <input
                type="text"
                value={apiKeyName}
                onChange={e => onApiKeyNameChange(e.target.value)}
                placeholder="用途說明（例如：測試、生產環境）"
                className="flex-1"
                onKeyDown={e => e.key === 'Enter' && onCreateApiKey()}
              />
              <button onClick={onCreateApiKey} disabled={apiKeyCreating || !apiKeyName.trim()}>
                {apiKeyCreating ? '建立中...' : '✓ 建立'}
              </button>
            </div>
          </>
        )}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-amber)' }}>
          現有 API Keys
        </h3>
        {apiKeysLoading ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
            載入中...
          </p>
        ) : apiKeys.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
            尚無 API Key
          </p>
        ) : (
          <ul className="file-list">
            {apiKeys.map(key => (
              <li key={key.id}>
                <div>
                  <div style={{ fontWeight: 'bold' }}>{key.name}</div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    {key.key_prefix} | {stores.find(s => s.name === key.store_name)?.display_name || key.store_name}
                    {key.prompt_index != null && (
                      <span style={{ color: 'var(--crystal-cyan)', marginLeft: '0.5rem' }}>
                        | {getApiKeyPromptLabel(key.prompt_index)}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => onDeleteApiKey(key.id)}
                  className="danger small"
                >
                  ✕ 刪除
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
