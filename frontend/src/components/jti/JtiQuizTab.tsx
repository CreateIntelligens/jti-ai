import { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Pencil, Trash2, ChevronDown, ChevronUp, Save, X, Upload, Download, Star } from 'lucide-react';
import * as api from '../../services/api';

interface JtiQuizTabProps {
       language: string;
}

type SubTab = 'questions' | 'results';

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
       const [loading, setLoading] = useState(false);
       const [successMsg, setSuccessMsg] = useState<string | null>(null);

       // Edit / Create
       const [editingId, setEditingId] = useState<string | null>(null);
       const [editData, setEditData] = useState<Partial<api.QuizQuestion>>({});
       const [creating, setCreating] = useState(false);
       const [newQuestion, setNewQuestion] = useState<api.QuizQuestion>({
              id: '', text: '', weight: 1, options: [
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

       // --- Quiz result set state ---
       const [quizSets, setQuizSets] = useState<api.QuizSet[]>([]);
       const [selectedQuizSetId, setSelectedQuizSetId] = useState<string>('default');
       const [creatingQuizSet, setCreatingQuizSet] = useState(false);
       const [newQuizSetName, setNewQuizSetName] = useState('');
       const [confirmDeleteQuizSet, setConfirmDeleteQuizSet] = useState<string | null>(null);

       // --- Quiz result state ---
       const [quizResults, setQuizResults] = useState<api.QuizResult[]>([]);
       const [quizLoading, setQuizLoading] = useState(false);
       const [editQuizId, setEditQuizId] = useState<string | null>(null);
       const [editQuizData, setEditQuizData] = useState<Partial<api.QuizResult>>({});
       const [savingQuizResult, setSavingQuizResult] = useState(false);

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
                            api.listQuizQuestions(language, selectedBankId),
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
       }, [language, selectedBankId]);

       const loadQuizSets = useCallback(async () => {
              try {
                     const data = await api.listQuizSets(language);
                     setQuizSets(data.sets || []);
                     if (data.sets.length > 0 && !data.sets.find(s => s.set_id === selectedQuizSetId)) {
                            const active = data.sets.find(s => s.is_active);
                            setSelectedQuizSetId(active ? active.set_id : data.sets[0].set_id);
                     }
              } catch (e) {
                     console.error('Failed to load quiz sets:', e);
              }
       }, [language]); // eslint-disable-line react-hooks/exhaustive-deps

       const loadQuizResults = useCallback(async () => {
              setQuizLoading(true);
              try {
                     const data = await api.listQuizResults(language, selectedQuizSetId);
                     setQuizResults(data.results || []);
              } catch (e) {
                     console.error('Failed to load quiz results:', e);
              } finally {
                     setQuizLoading(false);
              }
       }, [language, selectedQuizSetId]);

       useEffect(() => { void loadBanks(); }, [loadBanks]);
       useEffect(() => { void loadQuizSets(); }, [loadQuizSets]);

       useEffect(() => {
              if (subTab === 'questions') void loadQuestions();
              else void loadQuizResults();
       }, [subTab, loadQuestions, loadQuizResults]);

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

       const handleExportQuizResults = async () => {
              try {
                     await api.exportQuizResultsCsv(language);
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('匯出測驗結果失敗: ' + msg);
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
                            id: '', text: '', weight: 1,
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
              setEditData({ text: q.text, weight: q.weight, options: [...q.options] });
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

       // --- Quiz Result Set actions ---
       const handleCreateQuizSet = async () => {
              if (!newQuizSetName.trim()) return;
              try {
                     const set = await api.createQuizSet(language, newQuizSetName.trim());
                     setCreatingQuizSet(false);
                     setNewQuizSetName('');
                     setSelectedQuizSetId(set.set_id);
                     await loadQuizSets();
                     showSuccess('✅ 已建立新測驗結果集');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('建立失敗: ' + msg);
              }
       };

       const handleDeleteQuizSet = async (setId: string) => {
              try {
                     await api.deleteQuizSet(language, setId);
                     setConfirmDeleteQuizSet(null);
                     if (selectedQuizSetId === setId) setSelectedQuizSetId('default');
                     await loadQuizSets();
                     showSuccess('✅ 已刪除測驗結果集');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('刪除失敗: ' + msg);
              }
       };

       const handleActivateQuizSet = async (setId: string) => {
              try {
                     await api.activateQuizSet(language, setId);
                     await loadQuizSets();
                     showSuccess('✅ 已切換使用中的測驗結果集');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('切換失敗: ' + msg);
              }
       };

       // --- Quiz Result CRUD ---
       const handleStartQuizEdit = (qr: api.QuizResult) => {
              setEditQuizId(qr.quiz_id);
              setEditQuizData({
                     title: qr.title, color_name: qr.color_name,
                     recommended_colors: [...qr.recommended_colors], description: qr.description,
              });
       };

       const handleSaveQuizResult = async () => {
              if (!editQuizId) return;
              setSavingQuizResult(true);
              try {
                     await api.updateQuizResult(language, editQuizId, editQuizData, selectedQuizSetId);
                     setEditQuizId(null);
                     setEditQuizData({});
                     await loadQuizResults();
                     showSuccess('✅ 已更新測驗結果');
              } catch (e) {
                     const msg = e instanceof Error ? e.message : String(e);
                     alert('更新失敗: ' + msg);
              } finally {
                     setSavingQuizResult(false);
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
                                   className={`jti-quiz-subtab ${subTab === 'results' ? 'active' : ''}`}
                                   onClick={() => setSubTab('results')}
                            >
                                   測驗結果
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
                                                               <input placeholder='分數 {"analyst":1}' value={JSON.stringify(opt.score)} onChange={e => updateNewOption(idx, 'score', e.target.value)} style={{ width: 140 }} />
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

                     {/* ========== Quiz Results Sub-tab ========== */}
                     {subTab === 'results' && (
                            <div className="jti-quiz-result-section">

                                   {/* Quiz Result Set Selector Bar */}
                                   <div className="jti-bank-bar">
                                          <div className="jti-bank-list">
                                                 {quizSets.map(set => (
                                                        <div
                                                               key={set.set_id}
                                                               className={`jti-bank-card ${selectedQuizSetId === set.set_id ? 'selected' : ''}`}
                                                               onClick={() => setSelectedQuizSetId(set.set_id)}
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
                                                                      <span className="jti-bank-count">{set.quiz_count} 項</span>
                                                                      {!set.is_active && (
                                                                             <button
                                                                                    className="jti-bank-activate-btn"
                                                                                    onClick={(e) => { e.stopPropagation(); handleActivateQuizSet(set.set_id); }}
                                                                                    title="設為使用中"
                                                                             >
                                                                                    啟用
                                                                             </button>
                                                                      )}
                                                                      {!set.is_default && (
                                                                             <button
                                                                                    className="jti-bank-delete-btn"
                                                                                    onClick={(e) => { e.stopPropagation(); setConfirmDeleteQuizSet(set.set_id); }}
                                                                                    title="刪除"
                                                                             >
                                                                                    <Trash2 size={11} />
                                                                             </button>
                                                                      )}
                                                               </div>

                                                               {confirmDeleteQuizSet === set.set_id && (
                                                                      <div className="jti-bank-delete-confirm" onClick={e => e.stopPropagation()}>
                                                                             <span>確定刪除？</span>
                                                                             <button onClick={() => handleDeleteQuizSet(set.set_id)}>刪除</button>
                                                                             <button className="cancel" onClick={() => setConfirmDeleteQuizSet(null)}>取消</button>
                                                                      </div>
                                                               )}
                                                        </div>
                                                 ))}

                                                 {quizSets.length < 3 && (
                                                        creatingQuizSet ? (
                                                               <div className="jti-bank-card creating">
                                                                      <input
                                                                             placeholder="結果集名稱"
                                                                             value={newQuizSetName}
                                                                             onChange={e => setNewQuizSetName(e.target.value)}
                                                                             onKeyDown={e => e.key === 'Enter' && handleCreateQuizSet()}
                                                                             autoFocus
                                                                      />
                                                                      <div className="jti-bank-create-actions">
                                                                             <button onClick={handleCreateQuizSet}>建立</button>
                                                                             <button className="cancel" onClick={() => { setCreatingQuizSet(false); setNewQuizSetName(''); }}>
                                                                                    <X size={12} />
                                                                             </button>
                                                                      </div>
                                                               </div>
                                                        ) : (
                                                               <button className="jti-bank-add" onClick={() => setCreatingQuizSet(true)}>
                                                                      <Plus size={14} /> 新增結果集
                                                               </button>
                                                        )
                                                 )}
                                          </div>
                                   </div>

                                   <div className="jti-quiz-toolbar" style={{ justifyContent: 'flex-end', marginBottom: '10px' }}>
                                          <button
                                                 className="jti-quiz-export-btn"
                                                 onClick={handleExportQuizResults}
                                                 title="匯出測驗結果 CSV"
                                                 disabled={!quizResults.length}
                                          >
                                                 <Download size={13} /> 匯出
                                          </button>
                                   </div>
                                   {quizLoading ? (
                                          <div className="jti-quiz-loading">載入中...</div>
                                   ) : (
                                          <div className="jti-quiz-result-list">
                                                 {quizResults.map(qr => (
                                                        <div key={qr.quiz_id} className="jti-quiz-result-card">
                                                               <div className="jti-quiz-result-card-header">
                                                                      <span className={`jti-quiz-result-badge jti-quiz-${qr.quiz_id}`}>{qr.color_name}</span>
                                                                      <span className="jti-quiz-result-title">{qr.title}</span>
                                                                      {selectedQuizSetId !== 'default' && (
                                                                             <button className="icon-btn" onClick={() => editQuizId === qr.quiz_id ? setEditQuizId(null) : handleStartQuizEdit(qr)}>
                                                                                    {editQuizId === qr.quiz_id ? <X size={14} /> : <Pencil size={14} />}
                                                                             </button>
                                                                      )}
                                                               </div>

                                                               {editQuizId === qr.quiz_id ? (
                                                                      <div className="jti-quiz-result-edit">
                                                                             <div className="jti-quiz-form-row">
                                                                                    <input placeholder="標題" value={editQuizData.title || ''} onChange={e => setEditQuizData({ ...editQuizData, title: e.target.value })} />
                                                                                    <input placeholder="色系名稱" value={editQuizData.color_name || ''} onChange={e => setEditQuizData({ ...editQuizData, color_name: e.target.value })} />
                                                                             </div>
                                                                             <input
                                                                                    placeholder="推薦色（逗號、頓號或空白分隔）"
                                                                                    value={(editQuizData.recommended_colors || []).join(', ')}
                                                                                    onChange={e => setEditQuizData({ ...editQuizData, recommended_colors: e.target.value.split(/[,、\s]+/).filter(Boolean) })}
                                                                             />
                                                                             <textarea placeholder="描述" value={editQuizData.description || ''} onChange={e => setEditQuizData({ ...editQuizData, description: e.target.value })} rows={4} />
                                                                             <div className="jti-quiz-form-actions">
                                                                                    <button onClick={handleSaveQuizResult} disabled={savingQuizResult}><Save size={14} /> {savingQuizResult ? '儲存中...' : '儲存'}</button>
                                                                                    <button className="cancel" onClick={() => setEditQuizId(null)}><X size={14} /> 取消</button>
                                                                             </div>
                                                                      </div>
                                                               ) : (
                                                                      <div className="jti-quiz-result-preview">
                                                                             <div className="jti-quiz-result-tags">
                                                                                    {qr.recommended_colors.map(c => (<span key={c} className="jti-quiz-result-tag">{c}</span>))}
                                                                             </div>
                                                                             <p className="jti-quiz-result-desc">{qr.description}</p>
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
