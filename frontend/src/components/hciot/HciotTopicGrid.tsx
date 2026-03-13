import type { ChangeEvent } from 'react';

import type { HciotLanguage, HciotTopic } from '../../config/hciotTopics';

interface HciotTopicGridProps {
  topics: HciotTopic[];
  language: HciotLanguage;
  disabled?: boolean;
  onSelect: (topic: HciotTopic) => void;
  onSelectQuestion: (question: string) => void;
  selectedTopicId?: string | null;
  heading: string;
  subheading: string;
  questionHeading?: string;
  disabledMessage?: string | null;
}

export default function HciotTopicGrid({
  topics,
  language,
  disabled = false,
  onSelect,
  onSelectQuestion,
  selectedTopicId = null,
  heading,
  subheading,
  questionHeading,
  disabledMessage,
}: HciotTopicGridProps) {
  const findTopicById = (topicId: string) => topics.find((topic) => topic.id === topicId);
  const selectedTopic = selectedTopicId ? findTopicById(selectedTopicId) || null : null;
  const topicSelectPlaceholder = language === 'en' ? 'Select a topic…' : '選擇主題…';

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

      <select
        className="hciot-topic-select"
        value={selectedTopicId || ''}
        onChange={handleTopicChange}
        disabled={disabled}
      >
        <option value="" disabled>{topicSelectPlaceholder}</option>
        {topics.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.icon} {topic.labels[language]}
          </option>
        ))}
      </select>

      {selectedTopic ? (
        <div
          className="hciot-topic-question-panel"
          style={{ ['--topic-accent' as string]: selectedTopic.accent }}
        >
          <div className="hciot-topic-question-header">
            <p className="hciot-topic-question-kicker">{selectedTopic.summaries[language]}</p>
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
