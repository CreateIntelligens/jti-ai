import { useEffect, useState } from 'react';
import { useEscapeKey } from '../../../../hooks/useEscapeKey';
import { useOverlayPressClose } from '../../../../hooks/useOverlayPressClose';
import { Image as ImageIcon, Plus, Upload, X } from 'lucide-react';

import type { QaLanguage, QaAdminCategory } from '../../../../config/qaTopics';
import type { QaImage } from '../../../../services/api/_shared/qaKnowledge';
import DocumentToQaTab from './DocumentToQaTab';
import ImageUploadTab from './ImageUploadTab';
import QaUploadTab from './QaUploadTab';
import type { TopicLabels } from '../topicUtils';
import type { DeleteImageHandler, UploadedImageResult } from '../imageUpload';
import UploadTopicSelector from './UploadTopicSelector';
import { useUploadTopicSelection } from './uploadTopicSelection';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';

export {
  buildUploadTopicOptions,
  isUploadTopicSelectDisabled,
  readSavedTopicSelection,
} from './uploadTopicSelection';

type Tab = 'file' | 'qa' | 'image';

const TABS = [
  { id: 'file' as Tab, label: '上傳知識', icon: Upload },
  { id: 'qa' as Tab, label: '手動輸入', icon: Plus },
  { id: 'image' as Tab, label: '上傳圖片', icon: ImageIcon },
];

interface UploadDialogProps {
  open: boolean;
  language: QaLanguage;
  categories: QaAdminCategory[];
  availableImages: QaImage[];
  uploading: boolean;
  onClose: () => void;
  onUploadFile: (
    file: File,
    topicId: string | null,
    labels: TopicLabels | null,
  ) => Promise<{ name: string }>;
  onUploadComplete: (
    firstUploadedFileName: string | null,
    count: number,
    topicId?: string | null,
  ) => Promise<void>;
  onSubmitQA: (
    file: File,
    topicId: string,
    labels: TopicLabels,
    hiddenQuestions: string[],
  ) => Promise<{ name: string; uploaded_count: number }>;
  api: QaWorkspaceApiClient;
  disableAiQaExtraction?: boolean;
  resolveImageUrl?: (imageId?: string) => string | null;
  onUploadImage: (file: File, imageId?: string) => Promise<UploadedImageResult>;
  onDeleteImage?: DeleteImageHandler;
  onUploadImageComplete: (count: number) => Promise<void>;
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
  api,
  disableAiQaExtraction,
  resolveImageUrl,
  onUploadImage,
  onDeleteImage,
  onUploadImageComplete,
}: UploadDialogProps) {
  const [tab, setTab] = useState<Tab>('file');
  const overlayPressClose = useOverlayPressClose(onClose);
  const topic = useUploadTopicSelection(categories, open);
  const resolvedTopic = topic.resolvedTopic;

  useEffect(() => {
    if (open) {
      setTab('file');
    }
  }, [open]);

  useEscapeKey(onClose, open);

  if (!open) return null;

  return (
    <div className="qa-workspace-qa-overlay" {...overlayPressClose}>
      <div className="qa-workspace-qa-dialog">
        <div className="qa-workspace-qa-header">
          <h3>新增內容</h3>
          <button type="button" className="qa-workspace-qa-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="qa-workspace-upload-tabs" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              className={`qa-workspace-upload-tab${tab === item.id ? ' is-active' : ''}`}
              onClick={() => {
                setTab(item.id);
              }}
              aria-selected={tab === item.id}
            >
              <item.icon size={14} />
              {item.label}
            </button>
          ))}
        </div>

        {tab !== 'image' && (
          <UploadTopicSelector topic={topic} />
        )}

        {tab === 'file' && (
          <DocumentToQaTab
            open={open}
            language={language}
            uploading={uploading}
            resolvedTopic={resolvedTopic}
            topicSelectionIncomplete={topic.hasIncompleteNewLabels}
            onClose={onClose}
            onUploadFile={onUploadFile}
            onUploadComplete={onUploadComplete}
            api={api}
            disableAiQaExtraction={disableAiQaExtraction}
            availableImages={availableImages}
            resolveImageUrl={resolveImageUrl}
            onUploadImage={onUploadImage}
            onDeleteImage={onDeleteImage}
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
            resolveImageUrl={resolveImageUrl}
            onClose={onClose}
            onSubmitQA={onSubmitQA}
            onUploadComplete={onUploadComplete}
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
