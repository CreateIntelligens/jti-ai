import { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Pencil, Trash2, ChevronDown, ChevronUp, Save, X, Upload, Download, Star } from 'lucide-react';
import * as api from '../../services/api';

interface JtiQuizTabProps {
       language: string;
}

type SubTab = 'questions' | 'colors';

const EMPTY_OPTION: api.QuizQuestionOption = { id: '', text: '', score: {} };

export default function JtiQuizTab({ language }: JtiQuizTabProps) {
       const [subTab, setSubTab] = useState<SubTab>('questions');

       // --- Bank state ---
       const [banks, setBanks] = useState<api.QuizBank[]>([]);
       const [selectedBankId, setSelectedBankId] = useState<string>('default');
       const [creatingBank, setCreatingBank] = useState(false);
       const [newBankName, setNewBankName] = useState('');
       const [confirmDeleteBank, setConfirmDeleteBank] = useState<string | null>(null);

       // --- Question state ---
       const [questions, setQuestions] = useState<api.QuizQuestion[]>([]);
       const [stats, setStats] = useState<api.QuizBankStats | null>(null);
       const [category, setCategory] = useState<string>('');
       const [loading, setLoading] = useState(false);
       const [successMsg, setSuccessMsg] = useState<string | null>(null);

       // Edit / Create
       const [editingId, setEditingId] = useState<string | null>(null);
       const [editData, setEditData] = useState<Partial<api.QuizQuestion>>({});
       const [creating, setCreating] = useState(false);
       const [newQuestion, setNewQuestion] = useState<api.QuizQuestion>({
              id: '', text: '', category: 'personality', weight: 1, options: [
                     { ...EMPTY_OPTION, id: 'a' }, { ...EMPTY_OPTION, id: 'b' },
              ],
       });
       const [saving, setSaving] = useState(false);
       const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
       const [deleting, setDeleting] = useState(false);

       // Import
       const [importing, setImporting] = useState(false);
       const fileInputRef = useRef<HTMLInputElement>(null);

       // Expanded
       const [expandedId, setExpandedId] = useState<string | null>(null);

       // --- Color set state ---
       const [colorSets, setColorSets] = useState<api.ColorSet[]>([]);
       const [selectedColorSetId, setSelectedColorSetId] = useState<string>('default');
       const [creatingColorSet, setCreatingColorSet] = useState(false);
       const [newColorSetName, setNewColorSetName] = useState('');
       const [confirmDeleteColorSet, setConfirmDeleteColorSet] = useState<string | null>(null);

       // --- Color state ---
       const [colorResults, setColorResults] = useState<api.ColorResult[]>([]);
       const [colorLoading, setColorLoading] = useState(false);
       const [editColorId, setEditColorId] = useState<string | null>(null);
       const [editColorData, setEditColorData] = useState<Partial<api.ColorResult>>({});
       const [savingColor, setSavingColor] = useState(false);

       // --- Load data ---
       const loadBanks = useCallback(async () => {
              try {
                     const data = await api.listQuizBanks(language);
                     setBanks(data.banks || []);
                     // If selected bank no longer exists, reset
                     if (data.banks.length > 0 && !data.banks.find(b => b.bank_id === selectedBankId)) {
                            const active = data.banks.find(b => b.is_active);
                            setSelectedBankId(active ? active.bank_id : data.banks[0].bank_id);
                     }
              } catch (e) {
                     console.error('Failed to load banks:', e);
              }
       }, [language]); // eslint-disable-line react-hooks/exhaustive-deps

       const loadQuestions = useCallback(async () => {
              setLoading(true);
              try {
                     const [qData, sData] = await Promise.all([
                            api.listQuizQuestions(language, category || undefined, selectedBankId),
                            api.getQuizBankStats(language, selectedBankId),
                     ]);
                     const sortedQuestions = (qData.questions || []).sort((a: api.QuizQuestion, b: api.QuizQuestion) =>
                            a.id.localeCompare(b.id, undefined, { numeric: true, sensitivity: 'base' })
                     );
                     setQuestions(sortedQuestions);
                     setStats(sData);
              } catch (e) {
                     console.error('Failed to load questions:', e);
              } finally {
                     setLoading(false);
              }
       }, [language, category, selectedBankId]);

       const loadColorSets = useCallback(async () => {
              try {
                     const data = await api.listColorSets(language);
                     setColorSets(data.sets || []);
                     if (data.sets.length > 0 && !data.sets.find(s => s.set_id === selectedColorSetId)) {
                            const active = data.sets.find(s => s.is_active);
                            setSelectedColorSetId(active ? active.set_id : data.sets[0].set_id);
                     }
              } catch (e) {
                     console.error('Failed to load color sets:', e);
              }
       }, [language]); // eslint-disable-line react-hooks/exhaustive-deps

       const loadColors = useCallback(async () => {
              setColorLoading(true);
              try {
                     const data = await api.listColorResults(language, selectedColorSetId);
                     setColorResults(data.results || []);
              } catch (e) {
                     console.error('Failed to load color results:', e);
              } finally {
                     setColorLoading(false);
              }
       }, [language, selectedColorSetId]);

       useEffect(() => { void loadBanks(); }, [loadBanks]);
       useEffect(() => { void loadColorSets(); }, [loadColorSets]);

       useEffect(() => {
              if (subTab === 'questions') void loadQuestions();
              else void loadColors();
       }, [subTab, loadQuestions, loadColors]);

       const showSuccess = (msg: string) => {
              setSuccessMsg(msg);
              setTimeout(() => setSuccessMsg(null), 3000);
       };

       // --- Bank actions ---
       const handleCreateBank = async () => {
              if (!newBankName.trim()) return;
              try {
                     const bank = await api.createQuizBank(language, newBankName.trim());
                     setCreatingBank(false);
                     setNewBankName('');
                     setSelectedBankId(bank.bank_id);
                     await loadBanks();
                     showSuccess('✅ 已建立新題庫');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('建立失敗: ' + msg);
              }
       };

       const handleDeleteBank = async (bankId: string) => {
              try {
                     await api.deleteQuizBank(language, bankId);
                     setConfirmDeleteBank(null);
                     if (selectedBankId === bankId) setSelectedBankId('default');
                     await loadBanks();
                     showSuccess('✅ 已刪除題庫');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('刪除失敗: ' + msg);
              }
       };

       const handleActivateBank = async (bankId: string) => {
              try {
                     await api.activateQuizBank(language, bankId);
                     await loadBanks();
                     showSuccess('✅ 已切換使用中的題庫');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('切換失敗: ' + msg);
              }
       };

       // --- Import/Export ---
       const handleImport = async (file: File) => {
              setImporting(true);
              try {
                     const result = await api.importQuizBank(language, selectedBankId, file, false);
                     await loadQuestions();
                     await loadBanks();
                     showSuccess(`✅ 已匯入 ${result.count} 題`);
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('匯入失敗: ' + msg);
              } finally {
                     setImporting(false);
              }
       };

       const handleExport = async () => {
              try {
                     await api.exportQuizBankCsv(language, selectedBankId);
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('匯出失敗: ' + msg);
              }
       };

       const handleExportColors = async () => {
              try {
                     await api.exportColorResultsCsv(language);
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('匯出色彩結果失敗: ' + msg);
              }
       };

       // --- Question CRUD ---
       const handleCreateQuestion = async () => {
              if (!newQuestion.id || !newQuestion.text) return;
              setSaving(true);
              try {
                     await api.createQuizQuestion(language, newQuestion, selectedBankId);
                     setCreating(false);
                     setNewQuestion({
                            id: '', text: '', category: 'personality', weight: 1,
                            options: [{ ...EMPTY_OPTION, id: 'a' }, { ...EMPTY_OPTION, id: 'b' }],
                     });
                     await loadQuestions();
                     await loadBanks();
                     showSuccess('✅ 已新增題目');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('新增失敗: ' + msg);
              } finally {
                     setSaving(false);
              }
       };

       const handleStartEdit = (q: api.QuizQuestion) => {
              setEditingId(q.id);
              setEditData({ text: q.text, category: q.category, weight: q.weight, options: [...q.options] });
              setExpandedId(q.id);
       };

       const handleSaveEdit = async () => {
              if (!editingId) return;
              setSaving(true);
              try {
                     await api.updateQuizQuestion(language, editingId, editData, selectedBankId);
                     setEditingId(null);
                     setEditData({});
                     await loadQuestions();
                     showSuccess('✅ 已更新題目');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('更新失敗: ' + msg);
              } finally {
                     setSaving(false);
              }
       };

       const handleDelete = async () => {
              if (!confirmDeleteId) return;
              setDeleting(true);
              try {
                     await api.deleteQuizQuestion(language, confirmDeleteId, selectedBankId);
                     setConfirmDeleteId(null);
                     await loadQuestions();
                     await loadBanks();
                     showSuccess('✅ 已刪除題目');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('刪除失敗: ' + msg);
              } finally {
                     setDeleting(false);
              }
       };

       // --- Color Set actions ---
       const handleCreateColorSet = async () => {
              if (!newColorSetName.trim()) return;
              try {
                     const set = await api.createColorSet(language, newColorSetName.trim());
                     setCreatingColorSet(false);
                     setNewColorSetName('');
                     setSelectedColorSetId(set.set_id);
                     await loadColorSets();
                     showSuccess('✅ 已建立新色彩結果集');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('建立失敗: ' + msg);
              }
       };

       const handleDeleteColorSet = async (setId: string) => {
              try {
                     await api.deleteColorSet(language, setId);
                     setConfirmDeleteColorSet(null);
                     if (selectedColorSetId === setId) setSelectedColorSetId('default');
                     await loadColorSets();
                     showSuccess('✅ 已刪除色彩結果集');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('刪除失敗: ' + msg);
              }
       };

       const handleActivateColorSet = async (setId: string) => {
              try {
                     await api.activateColorSet(language, setId);
                     await loadColorSets();
                     showSuccess('✅ 已切換使用中的色彩結果集');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('切換失敗: ' + msg);
              }
       };

       // --- Color CRUD ---
       const handleStartColorEdit = (cr: api.ColorResult) => {
              setEditColorId(cr.color_id);
              setEditColorData({
                     title: cr.title, color_name: cr.color_name,
                     recommended_colors: [...cr.recommended_colors], description: cr.description,
              });
       };

       const handleSaveColor = async () => {
              if (!editColorId) return;
              setSavingColor(true);
              try {
                     await api.updateColorResult(language, editColorId, editColorData, selectedColorSetId);
                     setEditColorId(null);
                     setEditColorData({});
                     await loadColors();
                     showSuccess('✅ 已更新色彩結果');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('更新失敗: ' + msg);
              } finally {
                     setSavingColor(false);
              }
       };

       // --- Edit helpers ---
       const updateEditOption = (idx: number, field: string, value: string) => {
              const opts = [...(editData.options || [])];
              if (field === 'score') {
                     try { opts[idx] = { ...opts[idx], score: JSON.parse(value) }; } catch { /* ignore */ }
              } else {
                     opts[idx] = { ...opts[idx], [field]: value };
              }
              setEditData({ ...editData, options: opts });
       };

       const updateNewOption = (idx: number, field: string, value: string) => {
              const opts = [...newQuestion.options];
              if (field === 'score') {
                     try { opts[idx] = { ...opts[idx], score: JSON.parse(value) }; } catch { /* ignore */ }
              } else {
                     opts[idx] = { ...opts[idx], [field]: value };
              }
              setNewQuestion({ ...newQuestion, options: opts });
       };

       const allCategories = stats ? Object.keys(stats.categories) : [];
       const selectedBank = banks.find(b => b.bank_id === selectedBankId);

       return (
              <div className="jti-quiz-tab">
                     {/* Sub-tabs */}
                     <div className="jti-quiz-subtabs">
                            <button
                                   className={`jti-quiz-subtab ${subTab === 'questions' ? 'active' : ''}`}
                                   onClick={() => setSubTab('questions')}
                            >
                                   題庫管理
                            </button>
                            <button
                                   className={`jti-quiz-subtab ${subTab === 'colors' ? 'active' : ''}`}
                                   onClick={() => setSubTab('colors')}
                            >
                                   色彩結果
                            </button>
                     </div>

                     {successMsg && <div className="jti-quiz-success">{successMsg}</div>}

                     {/* ========== Questions Sub-tab ========== */}
                     {subTab === 'questions' && (
                            <div className="jti-quiz-questions">

                                   {/* Bank Selector Bar */}
                                   <div className="jti-bank-bar">
                                          <div className="jti-bank-list">
                                                 {banks.map(bank => (
                                                        <div
                                                               key={bank.bank_id}
                                                               className={`jti-bank-card ${selectedBankId === bank.bank_id ? 'selected' : ''}`}
                                                               onClick={() => setSelectedBankId(bank.bank_id)}
                                                        >
                                                               <div className="jti-bank-card-top">
                                                                      <span className="jti-bank-name">{bank.name || bank.bank_id}</span>
                                                                      {bank.is_active && (
                                                                             <span className="jti-bank-active-badge" title="使用中">
                                                                                    <Star size={10} /> 使用中
                                                                             </span>
                                                                      )}
                                                               </div>
                                                               <div className="jti-bank-card-bottom">
                                                                      <span className="jti-bank-count">{bank.question_count} 題</span>
                                                                      {!bank.is_active && (
                                                                             <button
                                                                                    className="jti-bank-activate-btn"
                                                                                    onClick={(e) => { e.stopPropagation(); handleActivateBank(bank.bank_id); }}
                                                                                    title="設為使用中"
                                                                             >
                                                                                    啟用
                                                                             </button>
                                                                      )}
                                                                      {!bank.is_default && (
                                                                             <button
                                                                                    className="jti-bank-delete-btn"
                                                                                    onClick={(e) => { e.stopPropagation(); setConfirmDeleteBank(bank.bank_id); }}
                                                                                    title="刪除"
                                                                             >
                                                                                    <Trash2 size={11} />
                                                                             </button>
                                                                      )}
                                                               </div>

                                                               {/* Inline delete confirm */}
                                                               {confirmDeleteBank === bank.bank_id && (
                                                                      <div className="jti-bank-delete-confirm" onClick={e => e.stopPropagation()}>
                                                                             <span>確定刪除？</span>
                                                                             <button onClick={() => handleDeleteBank(bank.bank_id)}>刪除</button>
                                                                             <button className="cancel" onClick={() => setConfirmDeleteBank(null)}>取消</button>
                                                                      </div>
                                                               )}
                                                        </div>
                                                 ))}

                                                 {/* Create new bank */}
                                                 {banks.length < 3 && (
                                                        creatingBank ? (
                                                               <div className="jti-bank-card creating">
                                                                      <input
                                                                             placeholder="題庫名稱"
                                                                             value={newBankName}
                                                                             onChange={e => setNewBankName(e.target.value)}
                                                                             onKeyDown={e => e.key === 'Enter' && handleCreateBank()}
                                                                             autoFocus
                                                                      />
                                                                      <div className="jti-bank-create-actions">
                                                                             <button onClick={handleCreateBank}>建立</button>
                                                                             <button className="cancel" onClick={() => { setCreatingBank(false); setNewBankName(''); }}>
                                                                                    <X size={12} />
                                                                             </button>
                                                                      </div>
                                                               </div>
                                                        ) : (
                                                               <button className="jti-bank-add" onClick={() => setCreatingBank(true)}>
                                                                      <Plus size={14} /> 新增題庫
                                                               </button>
                                                        )
                                                 )}
                                          </div>
                                   </div>

                                   {/* Import / Export row */}
                                   <div className="jti-quiz-toolbar">
                                          <select
                                                 className="jti-quiz-filter"
                                                 value={category}
                                                 onChange={e => setCategory(e.target.value)}
                                          >
                                                 <option value="">全部分類</option>
                                                 {allCategories.map(c => (
                                                        <option key={c} value={c}>{c}</option>
                                                 ))}
                                          </select>

                                          {selectedBankId !== 'default' && (
                                                 <>
                                                        <input
                                                               ref={fileInputRef}
                                                               type="file"
                                                               accept=".csv,.xlsx,.xls"
                                                               style={{ display: 'none' }}
                                                               onChange={e => {
                                                                      const f = e.target.files?.[0];
                                                                      if (f) handleImport(f);
                                                                      e.target.value = '';
                                                               }}
                                                        />
                                                        <button
                                                               className="jti-quiz-import-btn"
                                                               onClick={() => fileInputRef.current?.click()}
                                                               disabled={importing}
                                                               title="匯入 CSV / XLSX"
                                                        >
                                                               <Upload size={13} /> {importing ? '匯入中...' : '匯入'}
                                                        </button>
                                                 </>
                                          )}
                                          <button
                                                 className="jti-quiz-export-btn"
                                                 onClick={handleExport}
                                                 title="匯出 CSV"
                                                 disabled={!questions.length}
                                          >
                                                 <Download size={13} /> 匯出
                                          </button>
                                          {selectedBankId !== 'default' && (
                                                 <button
                                                        className="jti-quiz-add-btn"
                                                        onClick={() => setCreating(!creating)}
                                                 >
                                                        <Plus size={14} /> 新增
                                                 </button>
                                          )}
                                   </div>

                                   {/* Stats */}
                                   {stats && (
                                          <div className="jti-quiz-stats">
                                                 <span className="jti-quiz-stat-total">
                                                        {selectedBank?.name || selectedBankId}: <strong>{stats.total_questions}</strong> 題
                                                 </span>
                                                 {Object.entries(stats.categories).map(([cat, count]) => (
                                                        <span key={cat} className="jti-quiz-stat-cat">
                                                               {cat}: {count}
                                                        </span>
                                                 ))}
                                          </div>
                                   )}

                                   {/* Create form */}
                                   {creating && (
                                          <div className="jti-quiz-form">
                                                 <div className="jti-quiz-form-row">
                                                        <input
                                                               placeholder="題目 ID（如 c121）"
                                                               value={newQuestion.id}
                                                               onChange={e => setNewQuestion({ ...newQuestion, id: e.target.value })}
                                                        />
                                                        <select
                                                               value={newQuestion.category}
                                                               onChange={e => setNewQuestion({ ...newQuestion, category: e.target.value })}
                                                        >
                                                               {['personality', 'food', 'style', 'lifestyle', 'home', 'mood'].map(c => (
                                                                      <option key={c} value={c}>{c}</option>
                                                               ))}
                                                        </select>
                                                        <input
                                                               type="number"
                                                               placeholder="權重"
                                                               value={newQuestion.weight}
                                                               onChange={e => setNewQuestion({ ...newQuestion, weight: Number(e.target.value) })}
                                                               style={{ width: 70 }}
                                                        />
                                                 </div>
                                                 <textarea
                                                        placeholder="題目文字"
                                                        value={newQuestion.text}
                                                        onChange={e => setNewQuestion({ ...newQuestion, text: e.target.value })}
                                                        rows={2}
                                                 />
                                                 <div className="jti-quiz-options-header">選項：</div>
                                                 {newQuestion.options.map((opt, idx) => (
                                                        <div key={idx} className="jti-quiz-option-row">
                                                               <input placeholder="ID" value={opt.id} onChange={e => updateNewOption(idx, 'id', e.target.value)} style={{ width: 50 }} />
                                                               <input placeholder="選項文字" value={opt.text} onChange={e => updateNewOption(idx, 'text', e.target.value)} />
                                                               <input placeholder='分數 {"metal":1}' value={JSON.stringify(opt.score)} onChange={e => updateNewOption(idx, 'score', e.target.value)} style={{ width: 140 }} />
                                                        </div>
                                                 ))}
                                                 <div className="jti-quiz-form-actions">
                                                        <button onClick={handleCreateQuestion} disabled={saving}>{saving ? '儲存中...' : '新增'}</button>
                                                        <button className="cancel" onClick={() => setCreating(false)}>取消</button>
                                                 </div>
                                          </div>
                                   )}

                                   {/* Question list */}
                                   {loading ? (
                                          <div className="jti-quiz-loading">載入中...</div>
                                   ) : (
                                          <div className="jti-quiz-list">
                                                 {questions.map(q => (
                                                        <div key={q.id} className="jti-quiz-card">
                                                               <div className="jti-quiz-card-header" onClick={() => setExpandedId(expandedId === q.id ? null : q.id)}>
                                                                      <div className="jti-quiz-card-info">
                                                                             <span className="jti-quiz-card-id">{q.id}</span>
                                                                             <span className="jti-quiz-card-cat">{q.category}</span>
                                                                             <span className="jti-quiz-card-weight">×{q.weight}</span>
                                                                      </div>
                                                                      <div className="jti-quiz-card-text">{q.text}</div>
                                                                      <div className="jti-quiz-card-actions">
                                                                             {selectedBankId !== 'default' && (
                                                                                    <>
                                                                                           <button className="icon-btn" onClick={e => { e.stopPropagation(); handleStartEdit(q); }} title="編輯"><Pencil size={14} /></button>
                                                                                           <button className="icon-btn danger" onClick={e => { e.stopPropagation(); setConfirmDeleteId(q.id); }} title="刪除"><Trash2 size={14} /></button>
                                                                                    </>
                                                                             )}
                                                                             {expandedId === q.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                                                                      </div>
                                                               </div>

                                                               {expandedId === q.id && (
                                                                      <div className="jti-quiz-card-body">
                                                                             {editingId === q.id ? (
                                                                                    <div className="jti-quiz-edit-form">
                                                                                           <textarea value={editData.text || ''} onChange={e => setEditData({ ...editData, text: e.target.value })} rows={2} />
                                                                                           <div className="jti-quiz-form-row">
                                                                                                  <select value={editData.category || q.category} onChange={e => setEditData({ ...editData, category: e.target.value })}>
                                                                                                         {['personality', 'food', 'style', 'lifestyle', 'home', 'mood'].map(c => (
                                                                                                                <option key={c} value={c}>{c}</option>
                                                                                                         ))}
                                                                                                  </select>
                                                                                                  <input type="number" value={editData.weight ?? q.weight} onChange={e => setEditData({ ...editData, weight: Number(e.target.value) })} style={{ width: 70 }} />
                                                                                           </div>
                                                                                           <div className="jti-quiz-options-header">選項：</div>
                                                                                           {(editData.options || q.options).map((opt, idx) => (
                                                                                                  <div key={idx} className="jti-quiz-option-row">
                                                                                                         <input value={opt.id} onChange={e => updateEditOption(idx, 'id', e.target.value)} style={{ width: 50 }} />
                                                                                                         <input value={opt.text} onChange={e => updateEditOption(idx, 'text', e.target.value)} />
                                                                                                         <input value={JSON.stringify(opt.score)} onChange={e => updateEditOption(idx, 'score', e.target.value)} style={{ width: 140 }} />
                                                                                                  </div>
                                                                                           ))}
                                                                                           <div className="jti-quiz-form-actions">
                                                                                                  <button onClick={handleSaveEdit} disabled={saving}><Save size={14} /> {saving ? '儲存中...' : '儲存'}</button>
                                                                                                  <button className="cancel" onClick={() => { setEditingId(null); setEditData({}); }}><X size={14} /> 取消</button>
                                                                                           </div>
                                                                                    </div>
                                                                             ) : (
                                                                                    <div className="jti-quiz-options-view">
                                                                                           {q.options.map(opt => (
                                                                                                  <div key={opt.id} className="jti-quiz-option-view">
                                                                                                         <span className="option-id">{opt.id}.</span>
                                                                                                         <span className="option-text">{opt.text}</span>
                                                                                                         <span className="option-score">{Object.entries(opt.score).map(([k, v]) => `${k}:${v}`).join(', ')}</span>
                                                                                                  </div>
                                                                                           ))}
                                                                                    </div>
                                                                             )}
                                                                      </div>
                                                               )}

                                                               {confirmDeleteId === q.id && (
                                                                      <div className="jti-quiz-delete-confirm">
                                                                             <span>確定刪除題目 {q.id}？</span>
                                                                             <button onClick={handleDelete} disabled={deleting}>{deleting ? '刪除中...' : '確認刪除'}</button>
                                                                             <button className="cancel" onClick={() => setConfirmDeleteId(null)}>取消</button>
                                                                      </div>
                                                               )}
                                                        </div>
                                                 ))}
                                                 {questions.length === 0 && !loading && (
                                                        <div className="jti-quiz-empty">沒有找到題目</div>
                                                 )}
                                          </div>
                                   )}
                            </div>
                     )}

                     {/* ========== Colors Sub-tab ========== */}
                     {subTab === 'colors' && (
                            <div className="jti-quiz-colors">

                                   {/* Color Set Selector Bar */}
                                   <div className="jti-bank-bar">
                                          <div className="jti-bank-list">
                                                 {colorSets.map(set => (
                                                        <div
                                                               key={set.set_id}
                                                               className={`jti-bank-card ${selectedColorSetId === set.set_id ? 'selected' : ''}`}
                                                               onClick={() => setSelectedColorSetId(set.set_id)}
                                                        >
                                                               <div className="jti-bank-card-top">
                                                                      <span className="jti-bank-name">{set.name || set.set_id}</span>
                                                                      {set.is_active && (
                                                                             <span className="jti-bank-active-badge" title="使用中">
                                                                                    <Star size={10} /> 使用中
                                                                             </span>
                                                                      )}
                                                               </div>
                                                               <div className="jti-bank-card-bottom">
                                                                      <span className="jti-bank-count">{set.color_count} 色</span>
                                                                      {!set.is_active && (
                                                                             <button
                                                                                    className="jti-bank-activate-btn"
                                                                                    onClick={(e) => { e.stopPropagation(); handleActivateColorSet(set.set_id); }}
                                                                                    title="設為使用中"
                                                                             >
                                                                                    啟用
                                                                             </button>
                                                                      )}
                                                                      {!set.is_default && (
                                                                             <button
                                                                                    className="jti-bank-delete-btn"
                                                                                    onClick={(e) => { e.stopPropagation(); setConfirmDeleteColorSet(set.set_id); }}
                                                                                    title="刪除"
                                                                             >
                                                                                    <Trash2 size={11} />
                                                                             </button>
                                                                      )}
                                                               </div>

                                                               {confirmDeleteColorSet === set.set_id && (
                                                                      <div className="jti-bank-delete-confirm" onClick={e => e.stopPropagation()}>
                                                                             <span>確定刪除？</span>
                                                                             <button onClick={() => handleDeleteColorSet(set.set_id)}>刪除</button>
                                                                             <button className="cancel" onClick={() => setConfirmDeleteColorSet(null)}>取消</button>
                                                                      </div>
                                                               )}
                                                        </div>
                                                 ))}

                                                 {colorSets.length < 3 && (
                                                        creatingColorSet ? (
                                                               <div className="jti-bank-card creating">
                                                                      <input
                                                                             placeholder="結果集名稱"
                                                                             value={newColorSetName}
                                                                             onChange={e => setNewColorSetName(e.target.value)}
                                                                             onKeyDown={e => e.key === 'Enter' && handleCreateColorSet()}
                                                                             autoFocus
                                                                      />
                                                                      <div className="jti-bank-create-actions">
                                                                             <button onClick={handleCreateColorSet}>建立</button>
                                                                             <button className="cancel" onClick={() => { setCreatingColorSet(false); setNewColorSetName(''); }}>
                                                                                    <X size={12} />
                                                                             </button>
                                                                      </div>
                                                               </div>
                                                        ) : (
                                                               <button className="jti-bank-add" onClick={() => setCreatingColorSet(true)}>
                                                                      <Plus size={14} /> 新增結果集
                                                               </button>
                                                        )
                                                 )}
                                          </div>
                                   </div>

                                   <div className="jti-quiz-toolbar" style={{ justifyContent: 'flex-end', marginBottom: '10px' }}>
                                          <button
                                                 className="jti-quiz-export-btn"
                                                 onClick={handleExportColors}
                                                 title="匯出色彩結果 CSV"
                                                 disabled={!colorResults.length}
                                          >
                                                 <Download size={13} /> 匯出
                                          </button>
                                   </div>
                                   {colorLoading ? (
                                          <div className="jti-quiz-loading">載入中...</div>
                                   ) : (
                                          <div className="jti-color-list">
                                                 {colorResults.map(cr => (
                                                        <div key={cr.color_id} className="jti-color-card">
                                                               <div className="jti-color-card-header">
                                                                      <span className={`jti-color-badge jti-color-${cr.color_id}`}>{cr.color_name}</span>
                                                                      <span className="jti-color-title">{cr.title}</span>
                                                                      {selectedColorSetId !== 'default' && (
                                                                             <button className="icon-btn" onClick={() => editColorId === cr.color_id ? setEditColorId(null) : handleStartColorEdit(cr)}>
                                                                                    {editColorId === cr.color_id ? <X size={14} /> : <Pencil size={14} />}
                                                                             </button>
                                                                      )}
                                                               </div>

                                                               {editColorId === cr.color_id ? (
                                                                      <div className="jti-color-edit">
                                                                             <div className="jti-quiz-form-row">
                                                                                    <input placeholder="標題" value={editColorData.title || ''} onChange={e => setEditColorData({ ...editColorData, title: e.target.value })} />
                                                                                    <input placeholder="色系名稱" value={editColorData.color_name || ''} onChange={e => setEditColorData({ ...editColorData, color_name: e.target.value })} />
                                                                             </div>
                                                                             <input
                                                                                    placeholder="推薦色（逗號、頓號或空白分隔）"
                                                                                    value={(editColorData.recommended_colors || []).join(', ')}
                                                                                    onChange={e => setEditColorData({ ...editColorData, recommended_colors: e.target.value.split(/[,、\s]+/).filter(Boolean) })}
                                                                             />
                                                                             <textarea placeholder="描述" value={editColorData.description || ''} onChange={e => setEditColorData({ ...editColorData, description: e.target.value })} rows={4} />
                                                                             <div className="jti-quiz-form-actions">
                                                                                    <button onClick={handleSaveColor} disabled={savingColor}><Save size={14} /> {savingColor ? '儲存中...' : '儲存'}</button>
                                                                                    <button className="cancel" onClick={() => setEditColorId(null)}><X size={14} /> 取消</button>
                                                                             </div>
                                                                      </div>
                                                               ) : (
                                                                      <div className="jti-color-preview">
                                                                             <div className="jti-color-colors">
                                                                                    {cr.recommended_colors.map(c => (<span key={c} className="jti-color-tag">{c}</span>))}
                                                                             </div>
                                                                             <p className="jti-color-desc">{cr.description}</p>
                                                                      </div>
                                                               )}
                                                        </div>
                                                 ))}
                                          </div>
                                   )}
                            </div>
                     )}
              </div>
       );
}
