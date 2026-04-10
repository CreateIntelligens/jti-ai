import { useEffect, useMemo, useState } from 'react';
import { Image as ImageIcon, Plus, Upload, X } from 'lucide-react';
import HciotSelect from '../../HciotSelect';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage, HciotTopicCategory } from '../../../../services/api/hciot';
import FileUploadTab from './FileUploadTab';
import ImageUploadTab from './ImageUploadTab';
import QaUploadTab from './QaUploadTab';
import { buildLabels, NEW_VALUE, slugify, sortByLabel, type TopicLabels } from '../topicUtils';
import type { DeleteImageHandler, UploadedImageResult } from '../imageUpload';
import type { ResolvedUploadTopic } from './types';

type Tab = 'file' | 'qa' | 'image';

const TABS = [
  { id: 'file' as Tab, labelZh: '上傳知識檔', labelEn: 'Upload Files', icon: Upload },
  { id: 'qa' as Tab, labelZh: '手動輸入 Q&A', labelEn: 'Manual Q&A', icon: Plus },
  { id: 'image' as Tab, labelZh: '上傳圖片', labelEn: 'Upload Images', icon: ImageIcon },
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

function useTopicSelection(categories: HciotTopicCategory[], language: HciotLanguage, open: boolean) {
  const [categoryId, setCategoryId] = useState(DEFAULT_CATEGORY);
  const [topicId, setTopicId] = useState('');
  const [newCategoryZh, setNewCategoryZh] = useState('');
  const [newTopicZh, setNewTopicZh] = useState('');

  useEffect(() => {
    if (open) {
      setCategoryId(DEFAULT_CATEGORY);
      setTopicId('');
      setNewCategoryZh('');
      setNewTopicZh('');
    }
  }, [open]);

  const sortedCategories = useMemo(
    () => categories.slice().sort((left, right) => sortByLabel(left.labels[language], right.labels[language])),
    [categories, language],
  );

  const currentCategory = useMemo(
    () => (categoryId && categoryId !== NEW_VALUE ? categories.find((category) => category.id === categoryId) : null),
    [categories, categoryId],
  );

  const sortedTopics = useMemo(() => {
    if (!currentCategory) {
      return [];
    }
    return currentCategory.topics
      .slice()
      .sort((left, right) => sortByLabel(left.labels[language], right.labels[language]));
  }, [currentCategory, language]);

  const handleCategoryChange = (value: string) => {
    setCategoryId(value);
    setTopicId('');
    setNewTopicZh('');
    if (value !== NEW_VALUE) {
      setNewCategoryZh('');
    }
  };

  const handleTopicChange = (value: string) => {
    setTopicId(value);
    if (value !== NEW_VALUE) {
      setNewTopicZh('');
    }
  };

  const resolvedTopic = useMemo((): ResolvedUploadTopic | null => {
    const isNewCategory = categoryId === NEW_VALUE;
    const isNewTopic = topicId === NEW_VALUE;

    // 1. Resolve Category
    let catId = categoryId;
    let catLabels = { zh: '', en: '' };

    if (isNewCategory) {
      const b = buildLabels(newCategoryZh, '');
      if (!b) return null;
      catLabels = b;
      catId = slugify(catLabels.en);
    } else if (categoryId) {
      if (!currentCategory) return null;
      catId = categoryId;
      catLabels = { zh: currentCategory.labels.zh, en: currentCategory.labels.en };
    } else {
      return null;
    }

    // 2. Resolve Topic
    let topSlug = '';
    let topLabels = { zh: '', en: '' };

    if (isNewTopic) {
      const b = buildLabels(newTopicZh, '');
      if (b) {
        topLabels = b;
        topSlug = slugify(topLabels.en);
      }
    } else if (topicId) {
      const existingTopic = currentCategory?.topics.find((item) => item.id === topicId);
      if (existingTopic) {
        topSlug = topicId.split('/').pop() || topicId;
        topLabels = { zh: existingTopic.labels.zh, en: existingTopic.labels.en };
      }
    }

    const fullTopicId = topSlug ? `${catId}/${topSlug}` : catId;

    return {
      fullTopicId,
      labels: {
        categoryLabelZh: catLabels.zh,
        categoryLabelEn: catLabels.en,
        topicLabelZh: topLabels.zh,
        topicLabelEn: topLabels.en,
      },
    };
  }, [categoryId, topicId, newCategoryZh, newTopicZh, currentCategory]);

  return {
    categoryId,
    topicId,
    newCategoryZh,
    newTopicZh,
    setNewCategoryZh,
    setNewTopicZh,
    sortedCategories,
    sortedTopics,
    handleCategoryChange,
    handleTopicChange,
    resolvedTopic,
  };
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
  const topic = useTopicSelection(categories, language, open);
  const resolvedTopic = topic.resolvedTopic;

  useEffect(() => {
    if (open) {
      setTab('file');
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div className="hciot-qa-overlay" onClick={onClose}>
      <div className="hciot-qa-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="hciot-qa-header">
          <h3>{language === 'zh' ? '新增內容' : 'Add Content'}</h3>
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
              {language === 'zh' ? item.labelZh : item.labelEn}
            </button>
          ))}
        </div>

        {tab !== 'image' && (
          <div className="hciot-qa-topic-section">
            <label className="hciot-qa-topic-label">
              {language === 'zh' ? '指定科別 / 主題（可選）' : 'Category / Topic (optional)'}
            </label>
            <div className="hciot-qa-selectors">
              <HciotSelect
                className="hciot-file-select"
                value={topic.categoryId}
                onChange={topic.handleCategoryChange}
                options={[
                  { value: '', label: language === 'zh' ? '— 不指定 —' : '— None —' },
                  ...topic.sortedCategories.map((category) => ({ value: category.id, label: category.labels[language] })),
                  { value: NEW_VALUE, label: language === 'zh' ? '＋ 新增科別' : '+ New category' },
                ]}
              />
              <span className="hciot-file-path-separator">/</span>
              <HciotSelect
                className="hciot-file-select"
                value={topic.topicId}
                onChange={topic.handleTopicChange}
                disabled={!topic.categoryId || topic.categoryId === NEW_VALUE}
                options={[
                  { value: '', label: language === 'zh' ? '— 不指定 —' : '— None —' },
                  ...topic.sortedTopics.map((item) => ({ value: item.id, label: item.labels[language] })),
                  ...(topic.categoryId && topic.categoryId !== NEW_VALUE
                    ? [{ value: NEW_VALUE, label: language === 'zh' ? '＋ 新增主題' : '+ New topic' }]
                    : []),
                ]}
              />
            </div>

            {topic.categoryId === NEW_VALUE && (
              <div className="hciot-qa-new-fields">
                <input
                  className="hciot-file-input"
                  placeholder={language === 'zh' ? '新科別名稱' : 'New category name'}
                  value={topic.newCategoryZh}
                  onChange={(event) => topic.setNewCategoryZh(event.target.value)}
                />
              </div>
            )}

            {topic.topicId === NEW_VALUE && (
              <div className="hciot-qa-new-fields">
                <input
                  className="hciot-file-input"
                  placeholder={language === 'zh' ? '新主題名稱' : 'New topic name'}
                  value={topic.newTopicZh}
                  onChange={(event) => topic.setNewTopicZh(event.target.value)}
                />
              </div>
            )}
          </div>
        )}

        {tab === 'file' && (
          <FileUploadTab
            open={open}
            language={language}
            uploading={uploading}
            resolvedTopic={resolvedTopic}
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
            hasTopicSelection={Boolean(topic.categoryId || topic.newCategoryZh)}
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
