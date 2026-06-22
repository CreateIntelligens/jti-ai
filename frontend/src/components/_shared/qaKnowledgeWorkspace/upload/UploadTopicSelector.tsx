import QaSelect from '../../QaSelect';

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
      className="qa-workspace-file-input"
      placeholder={placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export default function UploadTopicSelector({ topic }: UploadTopicSelectorProps) {
  const isNewCategory = topic.categoryId === NEW_VALUE;
  const isNewTopic = topic.topicId === NEW_VALUE;
  const showNewFields = isNewCategory || isNewTopic;

  return (
    <div className="qa-workspace-qa-topic-section">
      <label className="qa-workspace-qa-topic-label">
        指定科別 / 主題
      </label>
      <div className="qa-workspace-qa-selectors">
        <QaSelect
          className="qa-workspace-file-select"
          value={topic.categoryId}
          onChange={topic.handleCategoryChange}
          options={[
            ...topic.sortedCategories.map((category) => ({ value: category.id, label: category.label })),
            { value: NEW_VALUE, label: '＋ 新增科別' },
          ]}
        />
        <span className="qa-workspace-file-path-separator">/</span>
        <QaSelect
          className="qa-workspace-file-select"
          value={topic.topicId}
          onChange={topic.handleTopicChange}
          disabled={isUploadTopicSelectDisabled(topic.categoryId)}
          options={buildUploadTopicOptions(topic.categoryId, topic.sortedTopics)}
        />
      </div>

      {showNewFields && (
        <div className="qa-workspace-qa-new-fields qa-workspace-qa-new-fields-row">
          {isNewCategory && (
            <LabelNameInput
              placeholder="新科別名稱"
              value={topic.newCategoryLabel}
              onChange={topic.setNewCategoryLabel}
            />
          )}
          {isNewTopic && (
            <LabelNameInput
              placeholder="新主題名稱"
              value={topic.newTopicLabel}
              onChange={topic.setNewTopicLabel}
            />
          )}
        </div>
      )}
    </div>
  );
}
