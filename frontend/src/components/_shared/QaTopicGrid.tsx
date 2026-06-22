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
                onClick={() => onSelectQuestion(question)}
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
