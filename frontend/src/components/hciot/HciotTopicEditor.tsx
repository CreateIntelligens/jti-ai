import { useState } from 'react';
import { ChevronDown, ChevronRight, Pencil, Trash2, Plus, Check, X, GripVertical } from 'lucide-react';
import type { HciotTopic, HciotTopicCategory } from '../../services/api/hciot';
import * as api from '../../services/api';
import ConfirmDialog from '../ConfirmDialog';
import {
  DEFAULT_TOPIC_LABEL,
  getErrorMessage,
  missingLabelMessage,
  slugify,
} from '../_shared/qaKnowledgeWorkspace/topicUtils';

interface Props {
  language: 'zh' | 'en';
  categories: HciotTopicCategory[];
  onCategoriesChange: (cats: HciotTopicCategory[]) => void;
}

type DeleteTarget = { type: 'category' | 'topic'; catId: string; topicId?: string };

function toQuestionLines(value: string): string[] {
  return value.split('\n').map((line) => line.trim()).filter(Boolean);
}

function getDeleteMessage(confirmDelete: DeleteTarget | null, _language: 'zh' | 'en'): string {
  if (!confirmDelete) return '';
  if (confirmDelete.type === 'category') {
    return '確定刪除此科別及其所有主題？';
  }
  return '確定刪除此主題？';
}

export default function HciotTopicEditor({ language, categories, onCategoriesChange }: Props) {
  const t = {
    title: '科別與題目',
    topics: '主題',
    questions: '題',
    edit: '編輯',
    delete: '刪除',
    rename: '改名',
    save: '儲存',
    saving: '儲存中…',
    cancel: '取消',
    addTopic: '新增主題',
    addCat: '新增科別',
    editQs: '編輯題目',
    noQs: '尚無題目',
    qsPlaceholder: '每行一題…',
    catPlaceholder: '名稱',
    newCat: '科別名稱',
    newTopic: '主題名稱',
    selectAll: language === 'zh' ? '顯示全部' : 'Select All',
  };

  const [expandedCatId, setExpandedCatId] = useState<string | null>(null);
  const [editingCatId, setEditingCatId] = useState<string | null>(null);
  const [editCatLabel, setEditCatLabel] = useState('');
  const [editingTopicId, setEditingTopicId] = useState<string | null>(null);
  const [editTopicLabel, setEditTopicLabel] = useState('');
  const [editingQuestions, setEditingQuestions] = useState<string | null>(null);
  const [questionsText, setQuestionsText] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<DeleteTarget | null>(null);
  const [addingCat, setAddingCat] = useState(false);
  const [newCatLabel, setNewCatLabel] = useState('');
  const [addingTopicInCat, setAddingTopicInCat] = useState<string | null>(null);
  const [newTopicLabel, setNewTopicLabel] = useState('');
  const [saving, setSaving] = useState(false);

  const reload = async () => {
    const data = await api.listHciotTopicsAdmin(language);
    onCategoriesChange(data.categories || []);
  };

  const totalQuestions = (cat: HciotTopicCategory) =>
    cat.topics.reduce((sum, topic) => sum + (topic.questions?.length ?? 0), 0);

  const resetCategoryDraft = () => { setAddingCat(false); setNewCatLabel(''); };
  const resetTopicDraft = () => { setAddingTopicInCat(null); setNewTopicLabel(''); };

  const runSavingAction = async (action: () => Promise<void>, onFinally?: () => void) => {
    setSaving(true);
    try { await action(); }
    catch (error) { alert(getErrorMessage(error)); }
    finally { setSaving(false); onFinally?.(); }
  };

  // ===== Category "edit" = update category_labels on all topics in that category =====

  const startEditCat = (cat: HciotTopicCategory) => {
    setEditingCatId(cat.id);
    setEditCatLabel(cat.label);
  };

  const saveEditCat = async (cat: HciotTopicCategory) => {
    const label = editCatLabel.trim();
    if (!label) {
      alert(missingLabelMessage('category', language));
      return;
    }
    await runSavingAction(async () => {
      await Promise.all(cat.topics.map((topic) => api.updateHciotTopic(topic.id, { category_labels: label }, language)));
      setEditingCatId(null);
      await reload();
    });
  };

  // "Add category" = add a first topic under the new category prefix
  const confirmAddCat = async () => {
    const catLabel = newCatLabel.trim();
    if (!catLabel) {
      alert(missingLabelMessage('category', language));
      return;
    }
    const catSlug = slugify(catLabel);
    if (!catSlug) return;
    const topicId = `${catSlug}/default`;
    await runSavingAction(async () => {
      await api.createHciotTopic(topicId, DEFAULT_TOPIC_LABEL, catLabel, undefined, language);
      resetCategoryDraft();
      await reload();
    });
  };

  // "Delete category" = delete all topics in that category
  const deleteCat = async (cat: HciotTopicCategory) => {
    await runSavingAction(
      async () => {
        await api.deleteHciotTopics(cat.topics.map((topic) => topic.id), language);
        if (expandedCatId === cat.id) setExpandedCatId(null);
        await reload();
      },
      () => setConfirmDelete(null),
    );
  };

  // ===== Topic CRUD (flat topic_id like "ortho-rehab/prp") =====

  const startEditTopic = (topic: HciotTopic) => {
    setEditingTopicId(topic.id);
    setEditTopicLabel(topic.label);
  };

  const saveEditTopic = async (topicId: string) => {
    const label = editTopicLabel.trim();
    if (!label) {
      alert(missingLabelMessage('topic', language));
      return;
    }
    await runSavingAction(async () => {
      await api.updateHciotTopic(topicId, { labels: label }, language);
      setEditingTopicId(null);
      await reload();
    });
  };

  const confirmAddTopic = async (cat: HciotTopicCategory) => {
    const label = newTopicLabel.trim();
    if (!label) {
      alert(missingLabelMessage('topic', language));
      return;
    }
    const topicSlug = slugify(label);
    if (!topicSlug) return;
    const topicId = `${cat.id}/${topicSlug}`;
    await runSavingAction(async () => {
      await api.createHciotTopic(topicId, label, cat.label, undefined, language);
      resetTopicDraft();
      await reload();
    });
  };

  const deleteTopic = async (topicId: string) => {
    await runSavingAction(
      async () => { await api.deleteHciotTopic(topicId, language); await reload(); },
      () => setConfirmDelete(null),
    );
  };

  // ===== Questions =====

  const startEditQuestions = (topic: HciotTopic) => {
    setEditingQuestions(topic.id);
    setQuestionsText((topic.questions ?? []).join('\n'));
  };

  const saveQuestions = async (topicId: string) => {
    const lines = toQuestionLines(questionsText);
    await runSavingAction(async () => {
      await api.updateHciotTopic(topicId, { questions: lines }, language);
      setEditingQuestions(null);
      await reload();
    });
  };

  const handleHeaderCheckboxChange = async (topic: HciotTopic, checked: boolean) => {
    const qs = topic.questions ?? [];
    const newHidden = checked ? [] : [...qs];
    await runSavingAction(async () => {
      await api.updateHciotTopic(topic.id, { hidden_questions: newHidden }, language);
      await reload();
    });
  };

  const handleQuestionCheckboxChange = async (topic: HciotTopic, question: string, checked: boolean) => {
    const hqs = topic.hidden_questions ?? [];
    let newHidden: string[];
    if (checked) {
      newHidden = hqs.filter((q) => q !== question);
    } else {
      newHidden = [...hqs, question];
    }
    await runSavingAction(async () => {
      await api.updateHciotTopic(topic.id, { hidden_questions: newHidden }, language);
      await reload();
    });
  };

  // ===== Delete confirm =====

  const handleDeleteConfirm = async () => {
    if (!confirmDelete) return;
    if (confirmDelete.type === 'category') {
      const cat = categories.find((c) => c.id === confirmDelete.catId);
      if (cat) await deleteCat(cat);
    } else if (confirmDelete.topicId) {
      await deleteTopic(confirmDelete.topicId);
    }
  };

  return (
    <div className="qa-te">
      <div className="qa-te-header">
        <h4 className="qa-te-title">
          科別與題目
        </h4>
      </div>

      {categories.map((cat) => {
        const isExpanded = expandedCatId === cat.id;
        const isEditingThis = editingCatId === cat.id;

        return (
          <div key={cat.id} className={`qa-te-cat${isExpanded ? ' expanded' : ''}`}>
            <div className="qa-te-cat-header">
              <button className="qa-te-cat-toggle" onClick={() => setExpandedCatId(isExpanded ? null : cat.id)}>
                {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </button>

              {isEditingThis ? (
                <div className="qa-te-inline-edit">
                  <input className="qa-kb-input" placeholder={t.catPlaceholder} value={editCatLabel}
                    onChange={(e) => setEditCatLabel(e.target.value)} autoFocus />
                  <button className="qa-te-icon-btn confirm" onClick={() => saveEditCat(cat)} disabled={saving}><Check size={14} /></button>
                  <button className="qa-te-icon-btn" onClick={() => setEditingCatId(null)}><X size={14} /></button>
                </div>
              ) : (
                <>
                  <span className="qa-te-cat-name" onClick={() => setExpandedCatId(isExpanded ? null : cat.id)}>
                    {cat.label}
                  </span>
                  <span className="qa-te-badge">
                    {cat.topics.length} {t.topics} · {totalQuestions(cat)} {t.questions}
                  </span>
                  <div className="qa-te-cat-actions">
                    <button className="qa-te-icon-btn" onClick={() => startEditCat(cat)} title={t.edit}>
                      <Pencil size={13} />
                    </button>
                    <button className="qa-te-icon-btn danger"
                      onClick={() => setConfirmDelete({ type: 'category', catId: cat.id })}
                      title={t.delete}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                </>
              )}
            </div>

            {isExpanded && (
              <div className="qa-te-topics">
                {cat.topics.map((topic) => {
                  const isEditingTopic = editingTopicId === topic.id;
                  const isEditingQs = editingQuestions === topic.id;
                  const qs = topic.questions ?? [];
                  const hiddenQuestions = topic.hidden_questions ?? [];
                  const hiddenQuestionSet = new Set(hiddenQuestions);
                  const visibleCount = qs.filter((q) => !hiddenQuestionSet.has(q)).length;
                  const allVisible = visibleCount === qs.length;
                  const isIndeterminate = visibleCount > 0 && visibleCount < qs.length;

                  return (
                    <div key={topic.id} className="qa-te-topic">
                      <div className="qa-te-topic-header">
                        <GripVertical size={14} className="qa-te-grip" />
                        {isEditingTopic ? (
                          <div className="qa-te-inline-edit">
                            <input className="qa-kb-input" placeholder={t.catPlaceholder} value={editTopicLabel}
                              onChange={(e) => setEditTopicLabel(e.target.value)} autoFocus />
                            <button className="qa-te-icon-btn confirm" onClick={() => saveEditTopic(topic.id)} disabled={saving}><Check size={14} /></button>
                            <button className="qa-te-icon-btn" onClick={() => setEditingTopicId(null)}><X size={14} /></button>
                          </div>
                        ) : (
                          <>
                            <span className="qa-te-topic-name">{topic.label}</span>
                            <span className="qa-te-badge small">{qs.length} {t.questions}</span>
                            <div className="qa-te-cat-actions">
                              <button className="qa-te-icon-btn" onClick={() => startEditTopic(topic)} title={t.rename}>
                                <Pencil size={12} />
                              </button>
                              <button className="qa-te-icon-btn danger"
                                onClick={() => setConfirmDelete({ type: 'topic', catId: cat.id, topicId: topic.id })}
                                title={t.delete}>
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </>
                        )}
                      </div>

                      <div className="qa-te-questions">
                        {isEditingQs ? (
                          <div className="qa-te-qs-edit">
                            <textarea className="qa-te-qs-textarea" value={questionsText}
                              onChange={(e) => setQuestionsText(e.target.value)}
                              placeholder={t.qsPlaceholder}
                              rows={Math.max(4, qs.length + 1)} />
                            <div className="qa-te-qs-actions">
                              <button className="qa-te-btn confirm" onClick={() => saveQuestions(topic.id)} disabled={saving}>
                                {saving ? t.saving : t.save}
                              </button>
                              <button className="qa-te-btn" onClick={() => setEditingQuestions(null)}>
                                {t.cancel}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            {qs.length > 0 ? (
                              <div className="qa-te-qs-container">
                                <div className="qa-te-qs-header">
                                  <label className="qa-te-qs-select-all">
                                    <input
                                      type="checkbox"
                                      className="qa-te-checkbox"
                                      checked={allVisible}
                                      ref={(el) => {
                                        if (el) el.indeterminate = isIndeterminate;
                                      }}
                                      onChange={(e) => handleHeaderCheckboxChange(topic, e.target.checked)}
                                      disabled={saving}
                                    />
                                    <span className="qa-te-qs-select-all-label">{t.selectAll}</span>
                                  </label>
                                </div>
                                <ul className="qa-te-qs-list custom-scrollbar">
                                  {qs.map((q, i) => {
                                    const isVisible = !hiddenQuestionSet.has(q);
                                    return (
                                      <li key={i} className="qa-te-q-item">
                                        <label className="qa-te-q-label-wrapper">
                                          <input
                                            type="checkbox"
                                            className="qa-te-checkbox"
                                            checked={isVisible}
                                            onChange={(e) => handleQuestionCheckboxChange(topic, q, e.target.checked)}
                                            disabled={saving}
                                          />
                                          <span className="qa-te-q-index">{i + 1}</span>
                                          <span className="qa-te-q-text">{q}</span>
                                        </label>
                                      </li>
                                    );
                                  })}
                                </ul>
                              </div>
                            ) : (
                              <p className="qa-te-empty">{t.noQs}</p>
                            )}
                            <button className="qa-te-btn edit-qs" onClick={() => startEditQuestions(topic)}>
                              <Pencil size={12} /> {t.editQs}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}

                {addingTopicInCat === cat.id ? (
                  <div className="qa-te-add-row">
                    <input className="qa-kb-input" placeholder={t.newTopic}
                      value={newTopicLabel} onChange={(e) => setNewTopicLabel(e.target.value)} autoFocus />
                    <button className="qa-te-icon-btn confirm" onClick={() => confirmAddTopic(cat)} disabled={saving}><Check size={14} /></button>
                    <button className="qa-te-icon-btn" onClick={resetTopicDraft}><X size={14} /></button>
                  </div>
                ) : (
                  <button className="qa-te-add-btn" onClick={() => setAddingTopicInCat(cat.id)}>
                    <Plus size={14} /> {t.addTopic}
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}

      {addingCat ? (
        <div className="qa-te-add-row">
          <input className="qa-kb-input" placeholder={t.newCat}
            value={newCatLabel} onChange={(e) => setNewCatLabel(e.target.value)} autoFocus />
          <button className="qa-te-icon-btn confirm" onClick={confirmAddCat} disabled={saving}><Check size={14} /></button>
          <button className="qa-te-icon-btn" onClick={resetCategoryDraft}><X size={14} /></button>
        </div>
      ) : (
        <button className="qa-te-add-btn" onClick={() => setAddingCat(true)} >
          <Plus size={14} /> {t.addCat}
        </button>
      )}

      <ConfirmDialog
        isOpen={!!confirmDelete}
        message={getDeleteMessage(confirmDelete, language)}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
