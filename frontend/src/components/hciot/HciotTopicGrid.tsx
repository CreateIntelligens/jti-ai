import HciotSelect from './HciotSelect';
import type { HciotCategory, HciotLanguage, HciotTopic } from '../../config/hciotTopics';

interface HciotTopicGridProps {
  topics: HciotTopic[];
  categories?: HciotCategory[];
  language: HciotLanguage;
  disabled?: boolean;
  onSelect: (topic: HciotTopic) => void;
  onSelectQuestion: (question: string) => void;
  onSelectCategory?: (categoryId: string | null) => void;
  selectedTopicId?: string | null;
  selectedCategoryId?: string | null;
  heading: string;
  subheading: string;
  questionHeading?: string;
  disabledMessage?: string | null;
}

export default function HciotTopicGrid({
  topics,
  categories = [],
  language,
  disabled = false,
  onSelect,
  onSelectQuestion,
  onSelectCategory,
  selectedTopicId = null,
  selectedCategoryId = null,
  heading,
  subheading,
  questionHeading,
  disabledMessage,
}: HciotTopicGridProps) {
  const selectedTopic = selectedTopicId ? topics.find((t) => t.id === selectedTopicId) ?? null : null;
  const categorySelectPlaceholder = language === 'en' ? 'All categories' : '全部科別';

  const handleCategoryChange = (value: string) => {
    onSelectCategory?.(value === '__all__' ? null : value);
  };

  const handleTopicChange = (value: string) => {
    const topic = topics.find((t) => t.id === value);
    if (topic) {
      onSelect(topic);
    }
  };

  return (
    <section className="hciot-topic-section">
      <div className="hciot-topic-panel-head">
        <p className="hciot-topic-kicker">{subheading}</p>
        <h3 className="hciot-topic-heading">{heading}</h3>
        {disabledMessage ? (
          <div className="hciot-topic-disabled">{disabledMessage}</div>
        ) : null}
      </div>

      {categories.length > 1 ? (
        <HciotSelect
          className="hciot-topic-select"
          value={selectedCategoryId || '__all__'}
          onChange={handleCategoryChange}
          disabled={disabled}
          options={[
            { value: '__all__', label: categorySelectPlaceholder },
            ...categories.map((cat) => ({ value: cat.id, label: cat.labels[language] })),
          ]}
        />
      ) : null}

      {topics.length > 0 ? (
        <HciotSelect
          className="hciot-topic-select"
          value={selectedTopicId || ''}
          onChange={handleTopicChange}
          disabled={disabled}
          options={topics.map((topic, index) => ({ value: topic.id || `topic-${index}`, label: topic.labels[language] }))}
        />
      ) : null}

      {selectedTopic ? (
        <div className="hciot-topic-question-panel">
          <p className="hciot-q-section-head">
            {questionHeading || `${selectedTopic.labels[language]} · 常見問題`}
          </p>
          <div className="hciot-topic-question-list custom-scrollbar">
            {selectedTopic.questions[language].map((question, index) => {
              const key = `${selectedTopic.id}-${index}`;
              return (
                <button
                  key={key}
                  type="button"
                  className="hciot-topic-question-chip"
                  onClick={() => onSelectQuestion(question)}
                  disabled={disabled}
                >
                  <span className="hciot-topic-question-index">{index + 1}</span>
                  <span className="hciot-topic-question-label">{question}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}
