import { ChevronRight } from 'lucide-react';
import type { QaCategory } from '../../config/qaTopics';

interface SuggestSidebarProps {
  categories: QaCategory[];
  selectedCategoryId: string | null;
  selectedTopicId: string | null;
  onSelectCategory: (categoryId: string) => void;
  onSelectTopic: (topicId: string) => void;
  onSelectQuestion: (question: string) => void;
  onClose: () => void;
  disabled?: boolean;
}

// Chat 右側常駐「常見問題」側欄：科別 → 主題 → 問題 三層 chips。
// 取代舊的彈出 overlay 面板，行為對齊設計稿。
export default function SuggestSidebar({
  categories,
  selectedCategoryId,
  selectedTopicId,
  onSelectCategory,
  onSelectTopic,
  onSelectQuestion,
  onClose,
  disabled = false,
}: SuggestSidebarProps) {
  const effectiveCategoryId = selectedCategoryId ?? categories[0]?.id ?? null;
  const activeCategory = categories.find((category) => category.id === effectiveCategoryId) ?? null;
  const topics = activeCategory?.topics ?? [];
  const activeTopic = topics.find((topic) => topic.id === selectedTopicId) ?? null;
  const questions = activeTopic?.questions ?? [];

  const hasCategories = categories.length > 0;
  const hasTopics = topics.length > 0;
  const hasQuestions = questions.length > 0;

  return (
    <aside className="suggest-sidebar" aria-label="常見問題">
      <div className="suggest-header">
        <span className="suggest-title">常見問題</span>
        <button
          type="button"
          className="icon-btn icon-btn-sm"
          title="收合"
          aria-label="收合常見問題"
          onClick={onClose}
        >
          <ChevronRight size={16} />
        </button>
      </div>

      <div className="suggest-body">
        {!hasCategories ? (
          <div className="suggest-empty">
            此知識庫尚未設定常見問題，可直接在左側輸入提問。
          </div>
        ) : (
          <>
            <div className="suggest-section">
              <div className="suggest-section-title">科別</div>
              <div className="suggest-chips">
                {categories.map((category) => (
                  <button
                    key={category.id}
                    type="button"
                    className={`suggest-chip${category.id === effectiveCategoryId ? ' active' : ''}`}
                    onClick={() => onSelectCategory(category.id)}
                  >
                    {category.label}
                  </button>
                ))}
              </div>
            </div>

            {hasTopics && (
              <div className="suggest-section">
                <div className="suggest-section-title">主題</div>
                <div className="suggest-chips">
                  {topics.map((topic) => (
                    <button
                      key={topic.id}
                      type="button"
                      className={`suggest-chip${topic.id === selectedTopicId ? ' active' : ''}`}
                      onClick={() => onSelectTopic(topic.id)}
                    >
                      {topic.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {hasQuestions ? (
              <div className="suggest-section">
                <div className="suggest-section-title">
                  {activeTopic ? `${activeTopic.label} · 常見問題` : '常見問題'}
                </div>
                <div className="suggest-questions">
                  {questions.map((question, index) => (
                    <button
                      key={question}
                      type="button"
                      className="suggest-question"
                      disabled={disabled}
                      onClick={() => onSelectQuestion(question)}
                    >
                      <span className="suggest-question-n">{index + 1}</span>
                      <span className="suggest-question-text">{question}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              hasTopics && (
                <div className="suggest-hint">選擇上方主題即可看到常見問題</div>
              )
            )}
          </>
        )}
      </div>
    </aside>
  );
}
