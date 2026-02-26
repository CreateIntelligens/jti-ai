import { useEffect, useState } from 'react';
import { Lock, Copy } from 'lucide-react';
import ConfirmDialog from '../ConfirmDialog';
import type { JtiRuntimeSettings } from '../../services/api';

interface Prompt {
  id: string;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
  is_default?: boolean;
  readonly?: boolean;
  is_active?: boolean;
}

type RuntimeSettings = JtiRuntimeSettings;
type RuntimeRuleSections = JtiRuntimeSettings['response_rule_sections']['zh'];

export interface JtiPersonaTabProps {
  prompts: Prompt[];
  maxCustom: number;
  loading: boolean;
  successMsg: string | null;
  language?: string;
  onSetActive: (promptId: string | null) => Promise<void>;
  onCloneDefault: () => Promise<void>;
  cloning: boolean;
  onCreate: (name: string, content: string) => Promise<void>;
  creating: boolean;
  onStartEdit: (prompt: Prompt) => void;
  editingId: string | null;
  editName: string;
  editContent: string;
  onEditNameChange: (name: string) => void;
  onEditContentChange: (content: string) => void;
  onSaveEdit: () => Promise<void>;
  onCancelEdit: () => void;
  onDeleteClick: (promptId: string) => void;
  confirmDeleteId: string | null;
  deleting: boolean;
  onDeleteConfirm: () => Promise<void>;
  onDeleteCancel: () => void;
  runtimeSettings: RuntimeSettings | null;
  runtimePromptId: string;
  defaultRuntimeSettings: RuntimeSettings | null;
  savingRuntimeSettings: boolean;
  onSelectRuntimePrompt: (promptId: string) => Promise<void>;
  onSaveRuntimeSettings: (settings: RuntimeSettings, promptId: string) => Promise<void>;
}

const SYSTEM_DEFAULT_ID = 'system_default';

export default function JtiPersonaTab({
  prompts,
  maxCustom,
  loading,
  successMsg,
  language = 'zh',
  onSetActive,
  onCloneDefault,
  cloning,
  onCreate,
  creating,
  onStartEdit,
  editingId,
  editName,
  editContent,
  onEditNameChange,
  onEditContentChange,
  onSaveEdit,
  onCancelEdit,
  onDeleteClick,
  confirmDeleteId,
  deleting,
  onDeleteConfirm,
  onDeleteCancel,
  runtimeSettings,
  runtimePromptId,
  defaultRuntimeSettings,
  savingRuntimeSettings,
  onSelectRuntimePrompt,
  onSaveRuntimeSettings,
}: JtiPersonaTabProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [newName, setNewName] = useState('');
  const [newContent, setNewContent] = useState('');
  const [runtimeDraft, setRuntimeDraft] = useState<RuntimeSettings | null>(runtimeSettings);

  const currentLang = typeof language === 'string' && language.trim().toLowerCase().startsWith('en')
    ? 'en'
    : 'zh';
  const customPrompts = prompts.filter(p => p.id !== SYSTEM_DEFAULT_ID);
  const defaultPrompt = prompts.find(p => p.id === SYSTEM_DEFAULT_ID);
  const showRoleScopeField = currentLang !== 'zh';

  useEffect(() => {
    setRuntimeDraft(runtimeSettings);
  }, [runtimeSettings]);

  const toggleExpand = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set<string>();
      if (!prev.has(id)) {
        next.add(id);
      }
      return next;
    });
  };

  const handleToggleExpand = (id: string) => {
    const willExpand = !expandedIds.has(id);
    toggleExpand(id);
    if (willExpand) {
      void onSelectRuntimePrompt(id);
    }
  };

  const handleStartEdit = (prompt: Prompt) => {
    onStartEdit(prompt);
    if (!expandedIds.has(prompt.id)) {
      setExpandedIds(new Set([prompt.id]));
      void onSelectRuntimePrompt(prompt.id);
    }
  };

  const getPreview = (content: string, maxLines = 3) => {
    const lines = content.split('\n');
    if (lines.length <= maxLines) return content;
    return lines.slice(0, maxLines).join('\n') + '...';
  };

  const shouldShowExpandButton = (_content?: string, _isActive?: boolean) => true;

  const getExpandButtonText = (expanded: boolean, _isActive?: boolean) => {
    return expanded ? '收起完整內容' : '展開完整內容';
  };

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    const name = newName.trim() || `自訂人物設定 ${customPrompts.length + 1}`;
    await onCreate(name, newContent.trim());
    setNewName('');
    setNewContent('');
  };

  const updateRuleSection = (field: keyof RuntimeRuleSections, value: string) => {
    setRuntimeDraft(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        response_rule_sections: {
          ...prev.response_rule_sections,
          [currentLang]: {
            ...prev.response_rule_sections[currentLang],
            [field]: value,
          },
        },
      };
    });
  };

  const updateLengthLimit = (value: string) => {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed)) return;
    setRuntimeDraft(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        max_response_chars: parsed,
      };
    });
  };

  const renderReadonlyRuntimeSettings = (settings: RuntimeSettings | null) => {
    if (!settings) return null;

    return (
      <div className="jti-runtime-settings">
        <div className="jti-prompt-name-row">
          <span className="jti-prompt-name">回覆規則</span>
        </div>

        <div className="jti-runtime-readonly-item">
          <div className="jti-runtime-label">回覆字數上限（字元）</div>
          <div className="jti-runtime-readonly-value">{settings.max_response_chars}</div>
        </div>

        {showRoleScopeField && (
          <div className="jti-runtime-readonly-item">
            <div className="jti-runtime-label">角色與可做事項（{currentLang.toUpperCase()}）</div>
            <pre className="jti-prompt-content">
              {settings.response_rule_sections[currentLang].role_scope}
            </pre>
          </div>
        )}

        <div className="jti-runtime-readonly-item">
          <div className="jti-runtime-label">範圍限制（{currentLang.toUpperCase()}）</div>
          <pre className="jti-prompt-content">
            {settings.response_rule_sections[currentLang].scope_limits}
          </pre>
        </div>

        <div className="jti-runtime-readonly-item">
          <div className="jti-runtime-label">回覆格式規則（{currentLang.toUpperCase()}）</div>
          <pre className="jti-prompt-content">
            {settings.response_rule_sections[currentLang].response_style}
          </pre>
        </div>

        <div className="jti-runtime-readonly-item">
          <div className="jti-runtime-label">知識庫規則（{currentLang.toUpperCase()}）</div>
          <pre className="jti-prompt-content">
            {settings.response_rule_sections[currentLang].knowledge_rules}
          </pre>
        </div>
      </div>
    );
  };

  const renderRuntimeSettings = (targetPromptId: string) => {
    if (targetPromptId === SYSTEM_DEFAULT_ID) {
      return renderReadonlyRuntimeSettings(defaultRuntimeSettings);
    }
    if (!runtimeDraft || runtimePromptId !== targetPromptId) {
      return (
        <div className="jti-runtime-settings">
          <div className="jti-settings-loading">載入回覆規則中...</div>
        </div>
      );
    }

    return (
      <div className="jti-runtime-settings">
        <div className="jti-prompt-name-row">
          <span className="jti-prompt-name">回覆規則</span>
        </div>

        <label className="jti-runtime-label">回覆字數上限（字元）</label>
        <input
          type="number"
          min={30}
          max={600}
          className="jti-prompt-input"
          value={runtimeDraft.max_response_chars}
          onChange={e => updateLengthLimit(e.target.value)}
        />

        {showRoleScopeField && (
          <>
            <label className="jti-runtime-label">角色與可做事項（{currentLang.toUpperCase()}）</label>
            <textarea
              className="jti-prompt-textarea"
              rows={6}
              value={runtimeDraft.response_rule_sections[currentLang].role_scope}
              onChange={e => updateRuleSection('role_scope', e.target.value)}
              placeholder="可做事項..."
            />
          </>
        )}

        <label className="jti-runtime-label">範圍限制（{currentLang.toUpperCase()}）</label>
        <textarea
          className="jti-prompt-textarea"
          rows={6}
          value={runtimeDraft.response_rule_sections[currentLang].scope_limits}
          onChange={e => updateRuleSection('scope_limits', e.target.value)}
          placeholder="限制條件..."
        />

        <label className="jti-runtime-label">回覆格式規則（{currentLang.toUpperCase()}）</label>
        <textarea
          className="jti-prompt-textarea"
          rows={6}
          value={runtimeDraft.response_rule_sections[currentLang].response_style}
          onChange={e => updateRuleSection('response_style', e.target.value)}
          placeholder="回覆格式規則..."
        />

        <label className="jti-runtime-label">知識庫規則（{currentLang.toUpperCase()}）</label>
        <textarea
          className="jti-prompt-textarea"
          rows={6}
          value={runtimeDraft.response_rule_sections[currentLang].knowledge_rules}
          onChange={e => updateRuleSection('knowledge_rules', e.target.value)}
          placeholder="知識庫使用規則..."
        />

        <button
          className="jti-btn primary full-width"
          onClick={() => onSaveRuntimeSettings(runtimeDraft, targetPromptId)}
          disabled={savingRuntimeSettings}
        >
          {savingRuntimeSettings ? '儲存中...' : '儲存回覆規則'}
        </button>
      </div>
    );
  };

  if (loading) {
    return <div className="jti-settings-loading">載入中...</div>;
  }

  return (
    <>
      {successMsg && (
        <div className="jti-success-banner">{successMsg}</div>
      )}

      <div className="jti-prompt-list">
        {/* 預設人物設定（唯讀） */}
        {defaultPrompt && (
          <div className={`jti-prompt-card ${defaultPrompt.is_active ? 'active' : ''}`}>
            <div className="jti-prompt-card-header">
              <div className="jti-prompt-name-row">
                <Lock size={14} className="jti-prompt-lock-icon" />
                <span className="jti-prompt-name">{defaultPrompt.name}</span>
                <span className="jti-prompt-badge">預設</span>
                <span className="jti-prompt-badge readonly">唯讀</span>
                {defaultPrompt.is_active && (
                  <span className="jti-prompt-active-badge">使用中</span>
                )}
              </div>
              <div className="jti-prompt-actions">
                {!defaultPrompt.is_active && (
                  <button
                    className="jti-btn small primary"
                    onClick={() => onSetActive(null)}
                  >
                    啟用
                  </button>
                )}
                {customPrompts.length < maxCustom && (
                  <button
                    className="jti-btn small secondary"
                    onClick={onCloneDefault}
                    disabled={cloning}
                    title="複製預設內容到新的自訂人物設定"
                  >
                    <Copy size={12} className="jti-prompt-clone-icon" />
                    {cloning ? '複製中...' : '以此為基礎建立副本'}
                  </button>
                )}
                {shouldShowExpandButton(defaultPrompt.content, defaultPrompt.is_active) && (
                  <button
                    className="jti-btn small secondary jti-prompt-expand"
                    onClick={() => handleToggleExpand(defaultPrompt.id)}
                  >
                    {getExpandButtonText(expandedIds.has(defaultPrompt.id), defaultPrompt.is_active)}
                  </button>
                )}
              </div>
            </div>
            <div className="jti-prompt-preview">
              <pre className="jti-prompt-content">
                {expandedIds.has(defaultPrompt.id) ? defaultPrompt.content : getPreview(defaultPrompt.content)}
              </pre>
            </div>
            {expandedIds.has(defaultPrompt.id) && renderRuntimeSettings(defaultPrompt.id)}
          </div>
        )}

        {/* 自訂人物設定（可編輯） */}
        {customPrompts.map(prompt => (
          <div
            key={prompt.id}
            className={`jti-prompt-card ${prompt.is_active ? 'active' : ''}`}
          >
            {editingId === prompt.id ? (
              <div className="jti-prompt-edit">
                <input
                  type="text"
                  className="jti-prompt-input"
                  value={editName}
                  onChange={e => onEditNameChange(e.target.value)}
                  placeholder="名稱"
                />
                <textarea
                  className="jti-prompt-textarea"
                  value={editContent}
                  onChange={e => onEditContentChange(e.target.value)}
                  placeholder="人物設定內容..."
                  rows={10}
                />
                <div className="jti-prompt-edit-actions">
                  <button className="jti-btn primary" onClick={onSaveEdit}>
                    儲存
                  </button>
                  <button className="jti-btn secondary" onClick={onCancelEdit}>
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="jti-prompt-card-header">
                  <div className="jti-prompt-name-row">
                    <span className="jti-prompt-name">{prompt.name}</span>
                    <span className="jti-prompt-badge custom">自訂</span>
                    {prompt.is_active && (
                      <span className="jti-prompt-active-badge">啟用中</span>
                    )}
                  </div>
                  <div className="jti-prompt-actions">
                    {!prompt.is_active ? (
                      <button
                        className="jti-btn small primary"
                        onClick={() => onSetActive(prompt.id)}
                      >
                        啟用
                      </button>
                    ) : (
                      <button
                        className="jti-btn small secondary"
                        onClick={() => onSetActive(null)}
                      >
                        取消啟用
                      </button>
                    )}
                    <button
                      className="jti-btn small secondary"
                      onClick={() => handleStartEdit(prompt)}
                    >
                      編輯
                    </button>
                    <button
                      className="jti-btn small secondary"
                      onClick={() => onDeleteClick(prompt.id)}
                    >
                      刪除
                    </button>
                    {shouldShowExpandButton(prompt.content, prompt.is_active) && (
                      <button
                        className="jti-btn small secondary jti-prompt-expand"
                        onClick={() => handleToggleExpand(prompt.id)}
                      >
                        {getExpandButtonText(expandedIds.has(prompt.id), prompt.is_active)}
                      </button>
                    )}
                  </div>
                </div>
                <div className="jti-prompt-preview">
                  <pre className="jti-prompt-content">
                    {expandedIds.has(prompt.id) ? prompt.content : getPreview(prompt.content)}
                  </pre>
                </div>
              </>
            )}
            {(expandedIds.has(prompt.id) || editingId === prompt.id) && renderRuntimeSettings(prompt.id)}
          </div>
        ))}
      </div>

      {/* Create new persona */}
      {customPrompts.length < maxCustom ? (
        <div className="jti-prompt-create">
          <h3 className="jti-prompt-create-title">
            新增自訂人物設定（{customPrompts.length}/{maxCustom}）
          </h3>
          <input
            type="text"
            className="jti-prompt-input"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder="名稱（可選，預設自動命名）"
          />
          <textarea
            className="jti-prompt-textarea"
            value={newContent}
            onChange={e => setNewContent(e.target.value)}
            placeholder="人物設定內容..."
            rows={6}
          />
          <button
            className="jti-btn primary full-width"
            onClick={handleCreate}
            disabled={creating || !newContent.trim()}
          >
            {creating ? '建立中...' : '建立人物設定'}
          </button>
        </div>
      ) : (
        <div className="jti-prompt-limit">
          自訂人物設定已達上限（{maxCustom} 個）
        </div>
      )}

      <ConfirmDialog
        isOpen={!!confirmDeleteId}
        message="確定要刪除此人物設定嗎？"
        onConfirm={onDeleteConfirm}
        onCancel={onDeleteCancel}
        loading={deleting}
      />
    </>
  );
}
