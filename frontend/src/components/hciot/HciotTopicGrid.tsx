import HciotSelect from './HciotSelect';
import type { HciotCategory, HciotTopic } from '../../config/hciotTopics';

const ALL_CATEGORIES_VALUE = '__all__';
const TOPIC_PANEL_SUBHEADING = '先選主題，再選問題';
const TOPIC_PANEL_HEADING = '常用衛教主題';
const ALL_CATEGORIES_LABEL = '全部科別';

interface HciotTopicGridProps {
  topics: HciotTopic[];
  categories?: HciotCategory[];
  disabled?: boolean;
  onSelect: (topic: HciotTopic) => void;
  onSelectQuestion: (question: string) => void;
  onSelectCategory?: (categoryId: string | null) => void;
  selectedTopicId?: string | null;
  selectedCategoryId?: string | null;
  disabledMessage?: string | null;
}

export default function HciotTopicGrid({
  topics,
  categories = [],
  disabled = false,
  onSelect,
  onSelectQuestion,
  onSelectCategory,
  selectedTopicId = null,
  selectedCategoryId = null,
  disabledMessage,
}: HciotTopicGridProps) {
  const selectedTopic = selectedTopicId ? topics.find((t) => t.id === selectedTopicId) ?? null : null;

  const handleCategoryChange = (value: string) => {
    onSelectCategory?.(value === ALL_CATEGORIES_VALUE ? null : value);
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
        <p className="hciot-topic-kicker">{TOPIC_PANEL_SUBHEADING}</p>
        <h3 className="hciot-topic-heading">{TOPIC_PANEL_HEADING}</h3>
        {disabledMessage ? (
          <div className="hciot-topic-disabled">{disabledMessage}</div>
        ) : null}
      </div>

      {categories.length > 1 ? (
        <HciotSelect
          className="hciot-topic-select"
          value={selectedCategoryId || ALL_CATEGORIES_VALUE}
          onChange={handleCategoryChange}
          disabled={disabled}
          options={[
            { value: ALL_CATEGORIES_VALUE, label: ALL_CATEGORIES_LABEL },
            ...categories.map((cat) => ({ value: cat.id, label: cat.label })),
          ]}
        />
      ) : null}

      {topics.length > 0 ? (
        <HciotSelect
          className="hciot-topic-select"
          value={selectedTopicId || ''}
          onChange={handleTopicChange}
          disabled={disabled}
          options={topics.map((topic, index) => ({ value: topic.id || `topic-${index}`, label: topic.label }))}
        />
      ) : null}

      {selectedTopic ? (
        <div className="hciot-topic-question-panel">
          <p className="hciot-q-section-head">
            {selectedTopic.label} 常見問題
          </p>
          <div className="hciot-topic-question-list custom-scrollbar">
            {selectedTopic.questions.map((question, index) => {
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
