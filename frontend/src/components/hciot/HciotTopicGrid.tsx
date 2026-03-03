import type { HciotLanguage, HciotTopic } from '../../config/hciotTopics';

interface HciotTopicGridProps {
  topics: HciotTopic[];
  language: HciotLanguage;
  disabled?: boolean;
  onSelect: (topic: HciotTopic) => void;
  heading: string;
  subheading: string;
  disabledMessage?: string | null;
}

export default function HciotTopicGrid({
  topics,
  language,
  disabled = false,
  onSelect,
  heading,
  subheading,
  disabledMessage,
}: HciotTopicGridProps) {
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
            className="hciot-topic-chip"
            onClick={() => onSelect(topic)}
            disabled={disabled}
            style={{ ['--topic-accent' as string]: topic.accent }}
          >
            <span className="hciot-topic-icon" aria-hidden="true">{topic.icon}</span>
            <span className="hciot-topic-label">{topic.labels[language]}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
