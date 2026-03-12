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
  const selectedTopic = topics.find((topic) => topic.id === selectedTopicId) || null;

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

      <div className="hciot-topic-grid">
        {topics.map((topic) => (
          <button
            key={topic.id}
            type="button"
            className={`hciot-topic-chip${selectedTopicId === topic.id ? ' active' : ''}`}
            onClick={() => onSelect(topic)}
            disabled={disabled}
            style={{ ['--topic-accent' as string]: topic.accent }}
          >
            <span className="hciot-topic-icon" aria-hidden="true">{topic.icon}</span>
            <span className="hciot-topic-label">{topic.labels[language]}</span>
          </button>
        ))}
      </div>

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
