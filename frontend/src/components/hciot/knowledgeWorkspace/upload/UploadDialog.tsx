import { useEffect, useMemo, useState } from 'react';
import { useEscapeKey } from '../../../../hooks/useEscapeKey';
import { Image as ImageIcon, Plus, Upload, X } from 'lucide-react';
import HciotSelect from '../../HciotSelect';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage, HciotTopicCategory } from '../../../../services/api/hciot';
import FileUploadTab from './FileUploadTab';
import ImageUploadTab from './ImageUploadTab';
import QaUploadTab from './QaUploadTab';
import { NEW_VALUE, normalizeLabel, slugify, sortByLabel, type TopicLabels } from '../topicUtils';
import type { DeleteImageHandler, UploadedImageResult } from '../imageUpload';
import type { ResolvedUploadTopic } from './types';

type Tab = 'file' | 'qa' | 'image';

const TABS = [
  { id: 'file' as Tab, label: '上傳知識檔', icon: Upload },
  { id: 'qa' as Tab, label: '手動輸入 Q&A', icon: Plus },
  { id: 'image' as Tab, label: '上傳圖片', icon: ImageIcon },
];

interface UploadDialogProps {
  open: boolean;
  language: HciotLanguage;
  categories: HciotTopicCategory[];
  availableImages: HciotImage[];
  uploading: boolean;
  onClose: () => void;
  onUploadFile: (file: File, topicId: string | null, labels: TopicLabels | null) => Promise<{ name: string }>;
  onUploadComplete: (firstUploadedFileName: string | null, count: number) => Promise<void>;
  onSubmitQA: (file: File, topicId: string, labels: TopicLabels) => Promise<void>;
  onUploadImage: (file: File, imageId?: string) => Promise<UploadedImageResult>;
  onDeleteImage?: DeleteImageHandler;
  onUploadImageComplete: (count: number) => Promise<void>;
}

const DEFAULT_CATEGORY = 'other';
const LS_CATEGORY_KEY = 'hciot_upload_category';
const LS_TOPIC_KEY = 'hciot_upload_topic';

interface SavedTopicSelection {
  categoryId: string;
  topicId: string;
}

export function readSavedTopicSelection(categories: HciotTopicCategory[]): SavedTopicSelection {
  if (!categories.length) {
    return { categoryId: NEW_VALUE, topicId: NEW_VALUE };
  }

  const savedCategory = localStorage.getItem(LS_CATEGORY_KEY);
  const category = categories.find((item) => item.id === savedCategory) ?? categories[0];
  const categoryId = category?.id ?? DEFAULT_CATEGORY;
  const savedTopic = localStorage.getItem(LS_TOPIC_KEY);
  const topicId = savedTopic && category?.topics.some((topic) => topic.id === savedTopic)
    ? savedTopic
    : '';

  return { categoryId, topicId };
}

type UploadTopicOption = { value: string; label: string };

export function isUploadTopicSelectDisabled(categoryId: string): boolean {
  return !categoryId;
}

export function buildUploadTopicOptions(
  categoryId: string,
  sortedTopics: HciotTopicCategory['topics'],
): UploadTopicOption[] {
  return [
    { value: '', label: '— 不指定 —' },
    ...sortedTopics.map((t) => ({ value: t.id, label: t.label })),
    ...(categoryId ? [{ value: NEW_VALUE, label: '＋ 新增主題' }] : []),
  ];
}

function resolveTopicInfo(
  categoryId: string,
  topicId: string,
  newCategoryLabel: string,
  newTopicLabel: string,
  currentCategory: HciotTopicCategory | null | undefined,
): ResolvedUploadTopic | null {
  if (!categoryId) return null;

  let catId = categoryId;
  let categoryLabel = '';

  if (categoryId === NEW_VALUE) {
    const normalized = normalizeLabel(newCategoryLabel);
    if (!normalized) return null;
    categoryLabel = normalized;
    catId = slugify(categoryLabel);
  } else {
    if (!currentCategory) return null;
    categoryLabel = currentCategory.label;
  }

  let topSlug = '';
  let topicLabel = '';

  if (topicId === NEW_VALUE) {
    const normalized = normalizeLabel(newTopicLabel);
    if (normalized) {
      topicLabel = normalized;
      topSlug = slugify(topicLabel);
    }
  } else if (topicId && currentCategory) {
    const existing = currentCategory.topics.find((t) => t.id === topicId);
    if (existing) {
      topSlug = topicId.split('/').pop() || topicId;
      topicLabel = existing.label;
    }
  }

  return {
    fullTopicId: topSlug ? `${catId}/${topSlug}` : catId,
    labels: {
      categoryLabel,
      topicLabel,
    },
  };
}

function useTopicSelection(categories: HciotTopicCategory[], open: boolean) {
  const [categoryId, setCategoryId] = useState(NEW_VALUE);
  const [topicId, setTopicId] = useState(NEW_VALUE);
  const [newCategoryLabel, setNewCategoryLabel] = useState('');
  const [newTopicLabel, setNewTopicLabel] = useState('');

  useEffect(() => {
    if (!open) return;
    const savedSelection = readSavedTopicSelection(categories);
    setCategoryId(savedSelection.categoryId);
    setTopicId(savedSelection.topicId);
    setNewCategoryLabel('');
    setNewTopicLabel('');
  }, [open, categories]);

  const sortedCategories = useMemo(
    () => [...categories].sort((a, b) => sortByLabel(a.label, b.label)),
    [categories],
  );

  const currentCategory = useMemo(
    () => (categoryId && categoryId !== NEW_VALUE ? categories.find((c) => c.id === categoryId) : null),
    [categories, categoryId],
  );

  const sortedTopics = useMemo(() => {
    if (!currentCategory) return [];
    return [...currentCategory.topics].sort((a, b) => sortByLabel(a.label, b.label));
  }, [currentCategory]);

  const resolvedTopic = useMemo(
    () => resolveTopicInfo(categoryId, topicId, newCategoryLabel, newTopicLabel, currentCategory),
    [categoryId, topicId, newCategoryLabel, newTopicLabel, currentCategory],
  );

  const hasIncompleteNewLabels = (
    (categoryId === NEW_VALUE && !normalizeLabel(newCategoryLabel))
    || (topicId === NEW_VALUE && !normalizeLabel(newTopicLabel))
  );

  return {
    categoryId,
    topicId,
    newCategoryLabel,
    newTopicLabel,
    setNewCategoryLabel,
    setNewTopicLabel,
    sortedCategories,
    sortedTopics,
    handleCategoryChange: (value: string) => {
      setCategoryId(value);
      setTopicId(value === NEW_VALUE ? NEW_VALUE : '');
      setNewTopicLabel('');
      if (value !== NEW_VALUE) {
        setNewCategoryLabel('');
        localStorage.setItem(LS_CATEGORY_KEY, value);
        localStorage.removeItem(LS_TOPIC_KEY);
      } else {
        localStorage.removeItem(LS_CATEGORY_KEY);
        localStorage.removeItem(LS_TOPIC_KEY);
      }
    },
    handleTopicChange: (value: string) => {
      setTopicId(value);
      if (value !== NEW_VALUE) {
        setNewTopicLabel('');
        localStorage.setItem(LS_TOPIC_KEY, value);
      }
    },
    hasIncompleteNewLabels,
    resolvedTopic,
  };
}

interface TopicSelectorSectionProps {
  topic: ReturnType<typeof useTopicSelection>;
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

function TopicSelectorSection({ topic }: TopicSelectorSectionProps) {
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
            ...topic.sortedCategories.map((c) => ({ value: c.id, label: c.label })),
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

export default function UploadDialog({
  open,
  language,
  categories,
  availableImages,
  uploading,
  onClose,
  onUploadFile,
  onUploadComplete,
  onSubmitQA,
  onUploadImage,
  onDeleteImage,
  onUploadImageComplete,
}: UploadDialogProps) {
  const [tab, setTab] = useState<Tab>('file');
  const topic = useTopicSelection(categories, open);
  const resolvedTopic = topic.resolvedTopic;

  useEffect(() => {
    if (open) setTab('file');
  }, [open]);

  useEscapeKey(onClose, open);

  if (!open) return null;

  return (
    <div className="hciot-qa-overlay" onClick={onClose}>
      <div className="hciot-qa-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="hciot-qa-header">
          <h3>新增內容</h3>
          <button type="button" className="hciot-qa-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="hciot-upload-tabs" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              className={`hciot-upload-tab${tab === item.id ? ' is-active' : ''}`}
              onClick={() => setTab(item.id as Tab)}
              aria-selected={tab === item.id}
            >
              <item.icon size={14} />
              {item.label}
            </button>
          ))}
        </div>

        {tab !== 'image' && <TopicSelectorSection topic={topic} />}

        {tab === 'file' && (
          <FileUploadTab
            open={open}
            language={language}
            uploading={uploading}
            resolvedTopic={resolvedTopic}
            topicSelectionIncomplete={topic.hasIncompleteNewLabels}
            onClose={onClose}
            onUploadFile={onUploadFile}
            onUploadComplete={onUploadComplete}
          />
        )}

        {tab === 'qa' && (
          <QaUploadTab
            open={open}
            language={language}
            uploading={uploading}
            availableImages={availableImages}
            resolvedTopic={resolvedTopic}
            hasTopicSelection={Boolean(resolvedTopic)}
            onClose={onClose}
            onSubmitQA={onSubmitQA}
            onUploadImage={onUploadImage}
            onDeleteImage={onDeleteImage}
          />
        )}

        {tab === 'image' && (
          <ImageUploadTab
            open={open}
            language={language}
            onClose={onClose}
            onUploadImage={onUploadImage}
            onUploadImageComplete={onUploadImageComplete}
          />
        )}
      </div>
    </div>
  );
}
