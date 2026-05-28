import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, X } from 'lucide-react';
import * as api from '../services/api';
import AppSelect from './AppSelect';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { toErrorMessage } from '../utils/errors';
import { confirmDiscard } from '../utils/confirmDiscard';

interface PromptPanelProps {
  isOpen: boolean;
  onClose: () => void;
  currentStore: string | null;
  currentStoreName?: string | null;
  onRestartChat: () => void | Promise<void>;
  onShowStatus?: (msg: string) => void;
}

type RuleSectionKey = 'role_scope' | 'scope_limits' | 'response_style' | 'knowledge_rules';

const NEW_PROMPT_ID = '__new__';
const RULE_SECTION_KEYS: RuleSectionKey[] = [
  'role_scope',
  'scope_limits',
  'response_style',
  'knowledge_rules',
];

const RULE_SECTION_LABELS: Record<RuleSectionKey, string> = {
  role_scope: '角色與任務',
  scope_limits: '範圍限制',
  response_style: '回應風格',
  knowledge_rules: '知識庫使用規則',
};

const RULE_SECTION_PLACEHOLDERS: Record<RuleSectionKey, string> = {
  role_scope: '留空使用預設：根據知識庫內容回答…',
  scope_limits: '留空使用預設：以知識庫資料為主…',
  response_style: '留空使用預設：使用繁體中文回覆…',
  knowledge_rules: '留空使用預設：優先依據知識庫…',
};

interface RuleSections {
  role_scope?: string;
  scope_limits?: string;
  response_style?: string;
  knowledge_rules?: string;
}

interface Prompt {
  id: string;
  name: string;
  content: string;
  response_rule_sections?: { zh?: RuleSections; en?: RuleSections } | null;
  max_response_chars?: number | null;
  is_default?: boolean;
  readonly?: boolean;
  is_active?: boolean;
}

const SYSTEM_DEFAULT_PROMPT_ID = 'system_default';

interface DraftState {
  name: string;
  content: string;
  sections: RuleSections;
  max_response_chars: number;
}

function makeEmptySections(): RuleSections {
  return {
    role_scope: '',
    scope_limits: '',
    response_style: '',
    knowledge_rules: '',
  };
}

function makeRuleSections(source: RuleSections = {}): RuleSections {
  const sections = makeEmptySections();
  RULE_SECTION_KEYS.forEach((key) => {
    sections[key] = source[key] ?? '';
  });
  return sections;
}

function makeDraft(prompt: Prompt | null): DraftState {
  const sections = prompt?.response_rule_sections?.zh || {};
  return {
    name: prompt?.name ?? '',
    content: prompt?.content ?? '',
    sections: makeRuleSections(sections),
    max_response_chars: prompt?.max_response_chars ?? 0,
  };
}

function isDraftDirty(draft: DraftState, prompt: Prompt | null): boolean {
  const baseline = makeDraft(prompt);
  return JSON.stringify(draft) !== JSON.stringify(baseline);
}

function buildSectionsPayload(draft: DraftState): { zh: RuleSections } | null {
  const trimmed: RuleSections = {};
  RULE_SECTION_KEYS.forEach((key) => {
    const value = (draft.sections[key] || '').trim();
    if (value) {
      trimmed[key] = value;
    }
  });
  return Object.keys(trimmed).length > 0 ? { zh: trimmed } : null;
}

function getStoredSelectedModel(): string {
  return localStorage.getItem('selectedModel') || '';
}

function storeSelectedModel(modelId: string): void {
  localStorage.setItem('selectedModel', modelId);
}

function resolveSelectedModel(models: api.ModelInfo[], defaultModel: string): string {
  const storedModel = getStoredSelectedModel();
  return storedModel && models.some((model) => model.name === storedModel)
    ? storedModel
    : defaultModel;
}

export default function PromptPanel({
  isOpen,
  onClose,
  currentStore,
  currentStoreName,
  onRestartChat,
  onShowStatus,
}: PromptPanelProps) {
  const [promptTab, setPromptTab] = useState<'system' | 'model'>('system');
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState>(makeDraft(null));
  const [showSections, setShowSections] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [maxPrompts, setMaxPrompts] = useState(3);

  const [availableModels, setAvailableModels] = useState<api.ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState(getStoredSelectedModel);

  useEscapeKey(onClose, isOpen);

  useEffect(() => {
    if (isOpen && currentStore) void loadPrompts();
  }, [isOpen, currentStore]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;

    const loadModels = async () => {
      setModelsLoading(true);
      try {
        const { models, default_model } = await api.fetchModels();
        if (cancelled) return;

        setAvailableModels(models);
        const nextModel = resolveSelectedModel(models, default_model);
        setSelectedModel(nextModel);
        storeSelectedModel(nextModel);
      } catch {
        // Keep the previous local selection if model discovery is unavailable.
      } finally {
        if (!cancelled) {
          setModelsLoading(false);
        }
      }
    };

    void loadModels();
    return () => { cancelled = true; };
  }, [isOpen]);

  const editingPrompt = prompts.find((p) => p.id === editingId) || null;
  const isCreatingPrompt = editingId === NEW_PROMPT_ID;
  const dirty = editingId !== null && isDraftDirty(draft, editingPrompt);

  const resetEditor = () => {
    setEditingId(null);
    setDraft(makeDraft(null));
    setShowSections(false);
  };

  const loadPrompts = async () => {
    if (!currentStore) return;
    setLoading(true);
    try {
      const data = await api.listPrompts(currentStore);
      const next: Prompt[] = data.prompts || [];
      setPrompts(next);
      setActivePromptId(data.active_prompt_id ?? null);
      setMaxPrompts(data.max_prompts || 3);
      if (editingId && !next.some((p) => p.id === editingId)) {
        resetEditor();
      }
    } catch (e) {
      console.error('Failed to load prompts:', e);
    } finally {
      setLoading(false);
    }
  };

  const startEditing = (prompt: Prompt) => {
    if (dirty && !confirmDiscard('switch')) return;
    setEditingId(prompt.id);
    setDraft(makeDraft(prompt));
    const hasSections = Boolean(
      prompt.response_rule_sections?.zh && Object.keys(prompt.response_rule_sections.zh).length,
    );
    setShowSections(hasSections);
  };

  const cancelEditing = () => {
    if (dirty && !confirmDiscard('discard')) return;
    resetEditor();
  };

  const customPrompts = prompts.filter((p) => !p.readonly && p.id !== SYSTEM_DEFAULT_PROMPT_ID);

  const handleCreateBlank = () => {
    if (!currentStore || customPrompts.length >= maxPrompts) return;
    if (dirty && !confirmDiscard('discard')) return;
    setEditingId(NEW_PROMPT_ID);
    setDraft({
      name: `Prompt ${customPrompts.length + 1}`,
      content: '',
      sections: makeEmptySections(),
      max_response_chars: 0,
    });
    setShowSections(false);
  };

  const duplicateFromDefault = (source: Prompt) => {
    if (!currentStore || customPrompts.length >= maxPrompts) return;
    if (dirty && !confirmDiscard('discard')) return;
    const sections = source.response_rule_sections?.zh || {};
    setEditingId(NEW_PROMPT_ID);
    setDraft({
      name: `自訂 ${customPrompts.length + 1}`,
      content: source.content || '',
      sections: makeRuleSections(sections),
      max_response_chars: source.max_response_chars ?? 0,
    });
    setShowSections(Object.keys(sections).length > 0);
  };

  const handleSave = async () => {
    if (!currentStore) return;
    if (!draft.content.trim()) {
      alert('Persona 內容不可為空');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: draft.name.trim() || `Prompt ${customPrompts.length + 1}`,
        content: draft.content.trim(),
        response_rule_sections: buildSectionsPayload(draft),
        max_response_chars: draft.max_response_chars > 0 ? draft.max_response_chars : null,
      };

      if (isCreatingPrompt) {
        await api.createPrompt(
          currentStore,
          payload.name,
          payload.content,
          payload.response_rule_sections,
          payload.max_response_chars,
        );
        onShowStatus?.('✅ Prompt 已建立');
      } else if (editingId) {
        await api.updatePrompt(
          currentStore,
          editingId,
          payload.name,
          payload.content,
          payload.response_rule_sections,
          payload.max_response_chars,
        );
        onShowStatus?.('✅ Prompt 已更新');
        if (editingId === activePromptId) await onRestartChat();
      }
      await loadPrompts();
      resetEditor();
    } catch (e) {
      alert('儲存失敗: ' + toErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const handleSetActive = async (promptId: string | null) => {
    if (!currentStore) return;
    try {
      await api.setActivePrompt(currentStore, promptId);
      await loadPrompts();
      await onRestartChat();
      onShowStatus?.(promptId ? '✅ Prompt 已套用' : '✅ 已停用 Prompt');
    } catch (e) {
      alert('設定失敗: ' + toErrorMessage(e));
    }
  };

  const handleDelete = async (promptId: string) => {
    if (!currentStore || !confirm('確定要刪除此 Prompt 嗎？')) return;
    try {
      await api.deletePrompt(currentStore, promptId);
      if (editingId === promptId) {
        resetEditor();
      }
      await loadPrompts();
      if (promptId === activePromptId) await onRestartChat();
    } catch (e) {
      alert('刪除失敗: ' + toErrorMessage(e));
    }
  };

  const handleModelChange = async (modelId: string) => {
    setSelectedModel(modelId);
    storeSelectedModel(modelId);
    onShowStatus?.('✅ 模型已切換');
  };

  if (!isOpen) return null;

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">Prompt 設定</span>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="rp-body">
          {!currentStore ? (
            <div className="rp-list-empty">
              請先在左側選擇一個知識庫
            </div>
          ) : (
            <>
              <div className="rp-current-store">
                目前知識庫：{currentStoreName || currentStore}
              </div>

              <div className="prompt-tab-row">
                {([['system', '系統 Prompt'], ['model', '模型設定']] as const).map(
                  ([id, label]) => (
                    <button
                      key={id}
                      className={`prompt-tab${promptTab === id ? ' active' : ''}`}
                      onClick={() => setPromptTab(id)}
                    >
                      {label}
                    </button>
                  ),
                )}
              </div>

              {promptTab === 'system' && (
                <div className="rp-stack">
                  {loading ? (
                    <div className="rp-loading">載入中...</div>
                  ) : (
                    <>
                      {prompts.length > 0 && (
                        <div className="rp-stack">
                          {prompts.map((p) => {
                            const isEditing = editingId === p.id;
                            const isReadonly = p.readonly === true || p.id === SYSTEM_DEFAULT_PROMPT_ID;
                            const isActive = isReadonly
                              ? activePromptId === null
                              : p.id === activePromptId;
                            return (
                              <div key={p.id} className={`key-card${isEditing ? ' active' : ''}`}>
                                <div className="kc-info flex-1">
                                  <div className="kc-name-row">
                                    <span className="kc-name">{p.name}</span>
                                    {isReadonly && <span className="kc-badge">系統預設</span>}
                                    {isActive && <span className="kc-badge system">使用中</span>}
                                  </div>
                                  {!isEditing && (
                                    <div className="kc-meta kc-meta-pre">
                                      {p.content.length > 80 ? p.content.slice(0, 80) + '...' : p.content}
                                    </div>
                                  )}
                                </div>
                                {!isEditing && (
                                  <div className="rp-card-actions">
                                    {isReadonly ? (
                                      <button
                                        className="btn btn-ghost btn-sm"
                                        onClick={() => duplicateFromDefault(p)}
                                        disabled={customPrompts.length >= maxPrompts}
                                        title={
                                          customPrompts.length >= maxPrompts
                                            ? `已達 ${maxPrompts} 個自訂 Prompt 上限`
                                            : '複製預設內容並開始編輯'
                                        }
                                      >
                                        複製為自訂
                                      </button>
                                    ) : (
                                      <button className="btn btn-ghost btn-sm" onClick={() => startEditing(p)}>
                                        編輯
                                      </button>
                                    )}
                                    {!isActive && (
                                      <button
                                        className="btn btn-primary btn-sm"
                                        onClick={() => handleSetActive(isReadonly ? null : p.id)}
                                      >
                                        套用
                                      </button>
                                    )}
                                    {!isReadonly && (
                                      <button
                                        className="btn btn-danger btn-sm"
                                        onClick={() => handleDelete(p.id)}
                                      >
                                        刪除
                                      </button>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {editingId !== null && (
                        <div className="rp-edit-card">
                          <div className="field">
                            <label>名稱</label>
                            <input
                              className="input-base"
                              placeholder="Prompt 名稱"
                              value={draft.name}
                              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                            />
                          </div>

                          <div className="field">
                            <label>角色設定 (Persona)</label>
                            <textarea
                              className="textarea-base"
                              placeholder="例：你是一個知識庫問答助手…"
                              rows={6}
                              value={draft.content}
                              onChange={(e) => setDraft({ ...draft, content: e.target.value })}
                            />
                          </div>

                          <button
                            type="button"
                            className="rp-section-toggle"
                            onClick={() => setShowSections((s) => !s)}
                          >
                            {showSections ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            進階：分段規則 (留空使用預設)
                          </button>

                          {showSections && (
                            <div className="rp-stack">
                              {RULE_SECTION_KEYS.map((key) => (
                                <div key={key} className="field">
                                  <label>{RULE_SECTION_LABELS[key]}</label>
                                  <textarea
                                    className="textarea-base"
                                    rows={3}
                                    placeholder={RULE_SECTION_PLACEHOLDERS[key]}
                                    value={draft.sections[key] || ''}
                                    onChange={(e) =>
                                      setDraft({
                                        ...draft,
                                        sections: { ...draft.sections, [key]: e.target.value },
                                      })
                                    }
                                  />
                                </div>
                              ))}
                            </div>
                          )}

                          <div className="field">
                            <label>字數限制（0 = 不限制）</label>
                            <input
                              className="input-base"
                              type="number"
                              min={0}
                              max={600}
                              step={10}
                              value={draft.max_response_chars}
                              onChange={(e) =>
                                setDraft({
                                  ...draft,
                                  max_response_chars: Number(e.target.value) || 0,
                                })
                              }
                            />
                          </div>

                          <div className="rp-card-actions">
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={cancelEditing}
                              disabled={saving}
                            >
                              取消
                            </button>
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={handleSave}
                              disabled={saving || !draft.content.trim() || (!dirty && !isCreatingPrompt)}
                            >
                              {saving ? '儲存中...' : '儲存'}
                            </button>
                          </div>
                        </div>
                      )}

                      {editingId === null && customPrompts.length < maxPrompts && (
                        <button
                          className="btn btn-primary btn-sm self-start"
                          onClick={handleCreateBlank}
                        >
                          + 新增 Prompt
                        </button>
                      )}

                      <span className="field-hint">
                        最多 {maxPrompts} 個。儲存後若該 Prompt 已啟用，將在下次對話生效。
                      </span>
                    </>
                  )}
                </div>
              )}

              {promptTab === 'model' && (
                <div className="rp-stack-lg">
                  <div className="field">
                    <label>模型</label>
                    <AppSelect
                      value={selectedModel}
                      onChange={handleModelChange}
                      disabled={modelsLoading}
                      placeholder={modelsLoading ? '載入中…' : selectedModel}
                      options={
                        availableModels.length > 0
                          ? availableModels.map((m) => ({
                              value: m.name,
                              label: m.display_name,
                            }))
                          : selectedModel
                            ? [{ value: selectedModel, label: selectedModel }]
                            : []
                      }
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
