import HciotSelect from '../../HciotSelect';

import { NEW_VALUE } from '../topicUtils';
import {
  buildUploadTopicOptions,
  isUploadTopicSelectDisabled,
  type UploadTopicSelection,
} from './uploadTopicSelection';

interface UploadTopicSelectorProps {
  topic: UploadTopicSelection;
}

interface LabelNameInputProps {
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}

function LabelNameInput({ placeholder, value, onChange }: LabelNameInputProps) {
  return (
    <input
      className="hciot-file-input"
      placeholder={placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export default function UploadTopicSelector({ topic }: UploadTopicSelectorProps) {
  return (
    <div className="hciot-qa-topic-section">
      <label className="hciot-qa-topic-label">
        指定科別 / 主題（可選）
      </label>
      <div className="hciot-qa-selectors">
        <HciotSelect
          className="hciot-file-select"
          value={topic.categoryId}
          onChange={topic.handleCategoryChange}
          options={[
            ...topic.sortedCategories.map((category) => ({ value: category.id, label: category.label })),
            { value: NEW_VALUE, label: '＋ 新增科別' },
          ]}
        />
        <span className="hciot-file-path-separator">/</span>
        <HciotSelect
          className="hciot-file-select"
          value={topic.topicId}
          onChange={topic.handleTopicChange}
          disabled={isUploadTopicSelectDisabled(topic.categoryId)}
          options={buildUploadTopicOptions(topic.categoryId, topic.sortedTopics)}
        />
      </div>

      {topic.categoryId === NEW_VALUE && (
        <div className="hciot-qa-new-fields">
          <LabelNameInput
            placeholder="新科別名稱"
            value={topic.newCategoryLabel}
            onChange={topic.setNewCategoryLabel}
          />
        </div>
      )}

      {topic.topicId === NEW_VALUE && (
        <div className="hciot-qa-new-fields">
          <LabelNameInput
            placeholder="新主題名稱"
            value={topic.newTopicLabel}
            onChange={topic.setNewTopicLabel}
          />
        </div>
      )}
    </div>
  );
}
