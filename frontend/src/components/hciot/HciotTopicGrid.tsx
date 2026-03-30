import type { ChangeEvent } from 'react';

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
  const findTopicById = (topicId: string) => topics.find((topic) => topic.id === topicId);
  const selectedTopic = selectedTopicId ? findTopicById(selectedTopicId) || null : null;
  const categorySelectPlaceholder = language === 'en' ? 'All categories' : '全部科別';

  const handleCategoryChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    onSelectCategory?.(value || null);
  };

  const handleTopicChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const topic = findTopicById(event.target.value);
    if (topic) {
      onSelect(topic);
    }
  };

  return (
    <section className="hciot-topic-section">
      <div className="hciot-topic-header">
        <div>
          <p className="hciot-topic-kicker">{subheading}</p>
          <h3 className="hciot-topic-heading">{heading}</h3>
        </div>
        {disabledMessage ? (
          <div className="hciot-topic-disabled">{disabledMessage}</div>
        ) : null}
      </div>

      {categories.length > 1 ? (
        <select
          className="hciot-topic-select"
          value={selectedCategoryId || ''}
          onChange={handleCategoryChange}
          disabled={disabled}
        >
          <option value="">{categorySelectPlaceholder}</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.labels[language]}
            </option>
          ))}
        </select>
      ) : null}

      {topics.length > 0 ? (
        <select
          className="hciot-topic-select"
          value={selectedTopicId || ''}
          onChange={handleTopicChange}
          disabled={disabled}
        >
          {topics.map((topic, index) => (
            <option key={topic.id || `topic-${index}`} value={topic.id}>
              {topic.labels[language]}
            </option>
          ))}
        </select>
      ) : null}

      {selectedTopic ? (
        <div className="hciot-topic-question-panel">
          <div className="hciot-topic-question-header">
            <h4 className="hciot-topic-question-heading">
              {questionHeading || selectedTopic.labels[language]}
            </h4>
          </div>

          <div className="hciot-topic-question-list">
            {selectedTopic.questions[language].map((question, index) => (
              <button
                key={`${selectedTopic.id}-${question}`}
                type="button"
                className="hciot-topic-question-chip"
                onClick={() => onSelectQuestion(question)}
                disabled={disabled}
              >
                <span className="hciot-topic-question-index">{index + 1}</span>
                <span className="hciot-topic-question-label">{question}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
