import { useState } from 'react';
import { ChevronDown, ChevronRight, Pencil, Trash2, Plus, Check, X, GripVertical } from 'lucide-react';
import type { HciotLabels, HciotTopicCategory } from '../../services/api/hciot';
import * as api from '../../services/api';
import ConfirmDialog from '../ConfirmDialog';
import { slugify, getErrorMessage } from './knowledgeWorkspace/topicUtils';

interface Props {
  language: 'zh' | 'en';
  categories: HciotTopicCategory[];
  onCategoriesChange: (cats: HciotTopicCategory[]) => void;
}

type HciotTopic = HciotTopicCategory['topics'][number];
type DeleteTarget = { type: 'category' | 'topic'; catId: string; topicId?: string };

function buildLabels(zh: string, en: string): HciotLabels {
  return { zh: zh || en, en: en || zh };
}

function toQuestionLines(value: string): string[] {
  return value.split('\n').map((line) => line.trim()).filter(Boolean);
}

function getDeleteMessage(confirmDelete: DeleteTarget | null, language: 'zh' | 'en'): string {
  if (!confirmDelete) return '';
  if (confirmDelete.type === 'category') {
    return language === 'zh' ? '確定刪除此科別及其所有主題？' : 'Delete this category and all its topics?';
  }
  return language === 'zh' ? '確定刪除此主題？' : 'Delete this topic?';
}

export default function HciotTopicEditor({ language, categories, onCategoriesChange }: Props) {
  const [expandedCatId, setExpandedCatId] = useState<string | null>(null);
  const [editingCatId, setEditingCatId] = useState<string | null>(null);
  const [editCatLabels, setEditCatLabels] = useState({ zh: '', en: '' });
  const [editingTopicId, setEditingTopicId] = useState<string | null>(null);
  const [editTopicLabels, setEditTopicLabels] = useState({ zh: '', en: '' });
  const [editingQuestions, setEditingQuestions] = useState<string | null>(null);
  const [questionsText, setQuestionsText] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<DeleteTarget | null>(null);
  const [addingCat, setAddingCat] = useState(false);
  const [newCatZh, setNewCatZh] = useState('');
  const [newCatEn, setNewCatEn] = useState('');
  const [addingTopicInCat, setAddingTopicInCat] = useState<string | null>(null);
  const [newTopicZh, setNewTopicZh] = useState('');
  const [newTopicEn, setNewTopicEn] = useState('');
  const [saving, setSaving] = useState(false);

  const reload = async () => {
    const data = await api.listHciotTopicsAdmin();
    onCategoriesChange(data.categories || []);
  };

  const totalQuestions = (cat: HciotTopicCategory) =>
    cat.topics.reduce((sum, t) => sum + (t.questions?.[language]?.length ?? 0), 0);

  const resetCategoryDraft = () => { setAddingCat(false); setNewCatZh(''); setNewCatEn(''); };
  const resetTopicDraft = () => { setAddingTopicInCat(null); setNewTopicZh(''); setNewTopicEn(''); };

  const runSavingAction = async (action: () => Promise<void>, onFinally?: () => void) => {
    setSaving(true);
    try { await action(); }
    catch (error) { alert(getErrorMessage(error)); }
    finally { setSaving(false); onFinally?.(); }
  };

  // ===== Category "edit" = update category_labels on all topics in that category =====

  const startEditCat = (cat: HciotTopicCategory) => {
    setEditingCatId(cat.id);
    setEditCatLabels({ ...cat.labels });
  };

  const saveEditCat = async (cat: HciotTopicCategory) => {
    if (!editCatLabels.zh.trim() && !editCatLabels.en.trim()) return;
    await runSavingAction(async () => {
      await Promise.all(cat.topics.map((topic) => api.updateHciotTopic(topic.id, { category_labels: editCatLabels })));
      setEditingCatId(null);
      await reload();
    });
  };

  // "Add category" = add a first topic under the new category prefix
  const confirmAddCat = async () => {
    const catZh = newCatZh.trim();
    const catEn = newCatEn.trim();
    if (!catZh && !catEn) return;
    const catSlug = slugify(catEn || catZh);
    if (!catSlug) return;
    // Create a placeholder topic — user can rename it later
    const topicId = `${catSlug}/default`;
    const catLabels = buildLabels(catZh, catEn);
    const topicLabels = buildLabels(
      language === 'zh' ? '預設主題' : 'Default topic',
      'Default topic',
    );
    await runSavingAction(async () => {
      await api.createHciotTopic(topicId, topicLabels, catLabels);
      resetCategoryDraft();
      await reload();
    });
  };

  // "Delete category" = delete all topics in that category
  const deleteCat = async (cat: HciotTopicCategory) => {
    await runSavingAction(
      async () => {
        await Promise.all(cat.topics.map((topic) => api.deleteHciotTopic(topic.id)));
        if (expandedCatId === cat.id) setExpandedCatId(null);
        await reload();
      },
      () => setConfirmDelete(null),
    );
  };

  // ===== Topic CRUD (flat topic_id like "ortho-rehab/prp") =====

  const startEditTopic = (topic: HciotTopic) => {
    setEditingTopicId(topic.id);
    setEditTopicLabels({ ...topic.labels });
  };

  const saveEditTopic = async (topicId: string) => {
    if (!editTopicLabels.zh.trim() && !editTopicLabels.en.trim()) return;
    await runSavingAction(async () => {
      await api.updateHciotTopic(topicId, { labels: editTopicLabels });
      setEditingTopicId(null);
      await reload();
    });
  };

  const confirmAddTopic = async (cat: HciotTopicCategory) => {
    const zh = newTopicZh.trim();
    const en = newTopicEn.trim();
    if (!zh && !en) return;
    const topicSlug = slugify(en || zh);
    if (!topicSlug) return;
    const topicId = `${cat.id}/${topicSlug}`;
    await runSavingAction(async () => {
      await api.createHciotTopic(topicId, buildLabels(zh, en), cat.labels);
      resetTopicDraft();
      await reload();
    });
  };

  const deleteTopic = async (topicId: string) => {
    await runSavingAction(
      async () => { await api.deleteHciotTopic(topicId); await reload(); },
      () => setConfirmDelete(null),
    );
  };

  // ===== Questions =====

  const startEditQuestions = (topic: HciotTopic) => {
    setEditingQuestions(topic.id);
    setQuestionsText((topic.questions?.[language] ?? []).join('\n'));
  };

  const saveQuestions = async (topicId: string) => {
    const lines = toQuestionLines(questionsText);
    await runSavingAction(async () => {
      await api.updateHciotTopic(topicId, { questions: { zh: lines, en: lines } });
      setEditingQuestions(null);
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
    <div className="hciot-te">
      <div className="hciot-te-header">
        <h4 className="hciot-te-title">
          {language === 'zh' ? '科別與題目' : 'Categories & Topics'}
        </h4>
      </div>

      {categories.map((cat) => {
        const isExpanded = expandedCatId === cat.id;
        const isEditingThis = editingCatId === cat.id;

        return (
          <div key={cat.id} className={`hciot-te-cat${isExpanded ? ' expanded' : ''}`}>
            <div className="hciot-te-cat-header">
              <button className="hciot-te-cat-toggle" onClick={() => setExpandedCatId(isExpanded ? null : cat.id)}>
                {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </button>

              {isEditingThis ? (
                <div className="hciot-te-inline-edit">
                  <input className="hciot-kb-input" placeholder="中文" value={editCatLabels.zh}
                    onChange={(e) => setEditCatLabels(p => ({ ...p, zh: e.target.value }))} autoFocus />
                  <input className="hciot-kb-input" placeholder="English" value={editCatLabels.en}
                    onChange={(e) => setEditCatLabels(p => ({ ...p, en: e.target.value }))} />
                  <button className="hciot-te-icon-btn confirm" onClick={() => saveEditCat(cat)} disabled={saving}><Check size={14} /></button>
                  <button className="hciot-te-icon-btn" onClick={() => setEditingCatId(null)}><X size={14} /></button>
                </div>
              ) : (
                <>
                  <span className="hciot-te-cat-name" onClick={() => setExpandedCatId(isExpanded ? null : cat.id)}>
                    {cat.labels[language]}
                  </span>
                  <span className="hciot-te-badge">
                    {cat.topics.length} {language === 'zh' ? '主題' : 'topics'} · {totalQuestions(cat)} {language === 'zh' ? '題' : 'Q'}
                  </span>
                  <div className="hciot-te-cat-actions">
                    <button className="hciot-te-icon-btn" onClick={() => startEditCat(cat)} title={language === 'zh' ? '編輯' : 'Edit'}>
                      <Pencil size={13} />
                    </button>
                    <button className="hciot-te-icon-btn danger"
                      onClick={() => setConfirmDelete({ type: 'category', catId: cat.id })}
                      title={language === 'zh' ? '刪除' : 'Delete'}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                </>
              )}
            </div>

            {isExpanded && (
              <div className="hciot-te-topics">
                {cat.topics.map((topic) => {
                  const isEditingTopic = editingTopicId === topic.id;
                  const isEditingQs = editingQuestions === topic.id;
                  const qs = topic.questions?.[language] ?? [];

                  return (
                    <div key={topic.id} className="hciot-te-topic">
                      <div className="hciot-te-topic-header">
                        <GripVertical size={14} className="hciot-te-grip" />
                        {isEditingTopic ? (
                          <div className="hciot-te-inline-edit">
                            <input className="hciot-kb-input" placeholder="中文" value={editTopicLabels.zh}
                              onChange={(e) => setEditTopicLabels(p => ({ ...p, zh: e.target.value }))} autoFocus />
                            <input className="hciot-kb-input" placeholder="English" value={editTopicLabels.en}
                              onChange={(e) => setEditTopicLabels(p => ({ ...p, en: e.target.value }))} />
                            <button className="hciot-te-icon-btn confirm" onClick={() => saveEditTopic(topic.id)} disabled={saving}><Check size={14} /></button>
                            <button className="hciot-te-icon-btn" onClick={() => setEditingTopicId(null)}><X size={14} /></button>
                          </div>
                        ) : (
                          <>
                            <span className="hciot-te-topic-name">{topic.labels[language]}</span>
                            <span className="hciot-te-badge small">{qs.length} {language === 'zh' ? '題' : 'Q'}</span>
                            <div className="hciot-te-cat-actions">
                              <button className="hciot-te-icon-btn" onClick={() => startEditTopic(topic)} title={language === 'zh' ? '改名' : 'Rename'}>
                                <Pencil size={12} />
                              </button>
                              <button className="hciot-te-icon-btn danger"
                                onClick={() => setConfirmDelete({ type: 'topic', catId: cat.id, topicId: topic.id })}
                                title={language === 'zh' ? '刪除' : 'Delete'}>
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </>
                        )}
                      </div>

                      <div className="hciot-te-questions">
                        {isEditingQs ? (
                          <div className="hciot-te-qs-edit">
                            <textarea className="hciot-te-qs-textarea" value={questionsText}
                              onChange={(e) => setQuestionsText(e.target.value)}
                              placeholder={language === 'zh' ? '每行一題…' : 'One question per line…'}
                              rows={Math.max(4, qs.length + 1)} />
                            <div className="hciot-te-qs-actions">
                              <button className="hciot-te-btn confirm" onClick={() => saveQuestions(topic.id)} disabled={saving}>
                                {saving ? (language === 'zh' ? '儲存中…' : 'Saving…') : (language === 'zh' ? '儲存' : 'Save')}
                              </button>
                              <button className="hciot-te-btn" onClick={() => setEditingQuestions(null)}>
                                {language === 'zh' ? '取消' : 'Cancel'}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            {qs.length > 0 ? (
                              <ul className="hciot-te-qs-list custom-scrollbar">
                                {qs.map((q, i) => (
                                  <li key={i} className="hciot-te-q-item">
                                    <span className="hciot-te-q-index">{i + 1}</span>
                                    <span className="hciot-te-q-text">{q}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="hciot-te-empty">{language === 'zh' ? '尚無題目' : 'No questions yet'}</p>
                            )}
                            <button className="hciot-te-btn edit-qs" onClick={() => startEditQuestions(topic)}>
                              <Pencil size={12} /> {language === 'zh' ? '編輯題目' : 'Edit questions'}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}

                {addingTopicInCat === cat.id ? (
                  <div className="hciot-te-add-row">
                    <input className="hciot-kb-input" placeholder={language === 'zh' ? '主題中文名' : 'Topic name (zh)'}
                      value={newTopicZh} onChange={(e) => setNewTopicZh(e.target.value)} autoFocus />
                    <input className="hciot-kb-input" placeholder={language === 'zh' ? '主題英文名' : 'Topic name (en)'}
                      value={newTopicEn} onChange={(e) => setNewTopicEn(e.target.value)} />
                    <button className="hciot-te-icon-btn confirm" onClick={() => confirmAddTopic(cat)} disabled={saving}><Check size={14} /></button>
                    <button className="hciot-te-icon-btn" onClick={resetTopicDraft}><X size={14} /></button>
                  </div>
                ) : (
                  <button className="hciot-te-add-btn" onClick={() => setAddingTopicInCat(cat.id)}>
                    <Plus size={14} /> {language === 'zh' ? '新增主題' : 'Add topic'}
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}

      {addingCat ? (
        <div className="hciot-te-add-row" style={{ marginTop: '0.5rem' }}>
          <input className="hciot-kb-input" placeholder={language === 'zh' ? '科別中文名' : 'Category name (zh)'}
            value={newCatZh} onChange={(e) => setNewCatZh(e.target.value)} autoFocus />
          <input className="hciot-kb-input" placeholder={language === 'zh' ? '科別英文名' : 'Category name (en)'}
            value={newCatEn} onChange={(e) => setNewCatEn(e.target.value)} />
          <button className="hciot-te-icon-btn confirm" onClick={confirmAddCat} disabled={saving}><Check size={14} /></button>
          <button className="hciot-te-icon-btn" onClick={resetCategoryDraft}><X size={14} /></button>
        </div>
      ) : (
        <button className="hciot-te-add-btn" onClick={() => setAddingCat(true)} style={{ marginTop: '0.5rem' }}>
          <Plus size={14} /> {language === 'zh' ? '新增科別' : 'Add category'}
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
