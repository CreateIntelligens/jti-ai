import AppSelect from '../AppSelect';
import type { QaCategory, QaTopic } from '../../config/qaTopics';

const ALL_CATEGORIES_VALUE = '__all__';

export interface QaTopicGridProps {
  topics: QaTopic[];
  categories?: QaCategory[];
  disabled?: boolean;
  onSelect: (topic: QaTopic) => void;
  onSelectQuestion: (question: string) => void;
  onSelectCategory?: (categoryId: string | null) => void;
  selectedTopicId?: string | null;
  selectedCategoryId?: string | null;
  disabledMessage?: string | null;
  heading?: string;
  subheading?: string;
  allCategoriesLabel?: string;
}

export default function QaTopicGrid({
  topics,
  categories = [],
  disabled = false,
  onSelect,
  onSelectQuestion,
  onSelectCategory,
  selectedTopicId = null,
  selectedCategoryId = null,
  disabledMessage,
  heading = '常用衛教主題',
  subheading = '先選主題，再選問題',
  allCategoriesLabel = '全部科別',
}: QaTopicGridProps) {
  const selectedTopic = selectedTopicId
    ? topics.find((topic) => topic.id === selectedTopicId) ?? null
    : null;

  // 送出問題時帶上層級路徑前綴（分類/主題：問題），讓 AI 有完整脈絡。
  // category 從 topic 反查（QaTopic 不帶 categoryId，且分類下拉可停在「全部科別」，
  // 不能用畫面篩選值）。降級：無分類→主題：問題；無主題→純問題。
  const buildQuestionText = (question: string): string => {
    if (!selectedTopic) return question;
    const owningCategory = categories.find((category) =>
      category.topics.some((topic) => topic.id === selectedTopic.id),
    );
    const prefix = [owningCategory?.label, selectedTopic.label].filter(Boolean).join('/');
    return prefix ? `${prefix}：${question}` : question;
  };

  const handleCategoryChange = (value: string) => {
    onSelectCategory?.(value === ALL_CATEGORIES_VALUE ? null : value);
  };

  const handleTopicChange = (value: string) => {
    const topic = topics.find((item) => item.id === value);
    if (topic) onSelect(topic);
  };

  return (
    <section className="qa-topic-section">
      <div className="qa-topic-panel-head">
        <p className="qa-topic-kicker">{subheading}</p>
        <h3 className="qa-topic-heading">{heading}</h3>
        {disabledMessage ? (
          <div className="qa-topic-disabled">{disabledMessage}</div>
        ) : null}
      </div>

      {categories.length > 1 ? (
        <AppSelect
          className="qa-topic-select"
          contentClassName="qa-select-content"
          value={selectedCategoryId || ALL_CATEGORIES_VALUE}
          onChange={handleCategoryChange}
          disabled={disabled}
          options={[
            { value: ALL_CATEGORIES_VALUE, label: allCategoriesLabel },
            ...categories.map((category) => ({ value: category.id, label: category.label })),
          ]}
        />
      ) : null}

      {topics.length > 0 ? (
        <AppSelect
          className="qa-topic-select"
          contentClassName="qa-select-content"
          value={selectedTopicId || ''}
          onChange={handleTopicChange}
          disabled={disabled}
          options={topics.map((topic, index) => ({
            value: topic.id || `topic-${index}`,
            label: topic.label,
          }))}
        />
      ) : null}

      {selectedTopic ? (
        <div className="qa-topic-question-panel">
          <p className="qa-q-section-head">{selectedTopic.label} 常見問題</p>
          <div className="qa-topic-question-list custom-scrollbar">
            {selectedTopic.questions.map((question, index) => (
              <button
                key={`${selectedTopic.id}-${index}`}
                type="button"
                className="qa-topic-question-chip"
                onClick={() => onSelectQuestion(buildQuestionText(question))}
                disabled={disabled}
              >
                <span className="qa-topic-question-index">{index + 1}</span>
                <span className="qa-topic-question-label">{question}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
