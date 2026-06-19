import { useMemo } from 'react';
import * as gapi from '../../services/api/general';
import QaKnowledgeWorkspace, {
  type QaWorkspaceApiClient,
  type QaWorkspaceConfig,
} from '../_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';
// Shared QA workspace styles (originally authored under hciot/, app-wide CSS).
import '../../styles/hciot/workspace-upload.css';
import '../../styles/hciot/workspace-upload-images.css';
import '../../styles/hciot/workspace-upload-enhancements.css';
import '../../styles/hciot/workspace-upload-preview.css';
import '../../styles/hciot/workspace-upload-edit.css';

interface GeneralKnowledgeWorkspaceProps {
  active: boolean;
  storeName: string;
  onTopicsChanged?: () => Promise<void> | void;
}

// Build a workspace API client bound to one general store. The shared workspace
// passes a `language` arg into every method; general ignores it (the store is
// fixed by closure) and routes by store_name instead. AI Q&A extraction is
// disabled, so those methods are never called — they reject defensively.
function makeApi(storeName: string): QaWorkspaceApiClient {
  const extractionDisabled = () =>
    Promise.reject(new Error('QA extraction is disabled for general stores'));

  return {
    listKnowledgeFiles: () => gapi.listGeneralKnowledgeFiles(storeName),
    listTopicsAdmin: () => gapi.listGeneralTopicsAdmin(storeName),
    listImages: () => gapi.listGeneralImages(storeName),
    getReindexStatus: () => gapi.getGeneralStoreReindexStatus(storeName),
    reindex: () => gapi.reindexGeneralStore(storeName),
    getKnowledgeFileContent: (filename) => gapi.getGeneralKnowledgeFileContent(filename, storeName),
    uploadKnowledgeFileWithTopic: (opts) =>
      gapi.uploadGeneralKnowledgeFileWithTopic({
        storeName,
        file: opts.file,
        categoryId: opts.categoryId,
        topicId: opts.topicId,
        categoryLabel: opts.categoryLabel,
        topicLabel: opts.topicLabel,
        hiddenQuestions: opts.hiddenQuestions,
      }),
    deleteKnowledgeFile: (filename) => gapi.deleteGeneralKnowledgeFile(filename, storeName),
    updateTopic: (topicId, data) => gapi.updateGeneralTopic(storeName, topicId, data),
    reorderTopics: (topicIds) => gapi.reorderGeneralTopics(storeName, topicIds),
    setCategoryHidden: (categoryId, hidden) =>
      gapi.setGeneralCategoryHidden(storeName, categoryId, hidden),
    uploadImage: (file, imageId) => gapi.uploadGeneralImage(storeName, file, imageId),
    deleteImage: (imageId) => gapi.deleteGeneralImage(storeName, imageId),
    deleteUnusedImages: () =>
      Promise.resolve({ deleted_count: 0, deleted_image_ids: [] as string[] }),
    createTopic: (topicId, label, categoryLabel, questions) =>
      gapi.createGeneralTopic(storeName, topicId, label, categoryLabel, questions),
    updateKnowledgeFileMetadata: (filename, metadata) =>
      gapi.updateGeneralKnowledgeFileMetadata(filename, metadata, storeName),
    updateKnowledgeFileContent: (filename, content) =>
      gapi.updateGeneralKnowledgeFileContent(filename, content, storeName),
    downloadKnowledgeFile: (filename) => gapi.downloadGeneralKnowledgeFile(filename, storeName),
    getTopicMergedCsv: (topicId) => gapi.getGeneralTopicMergedCsv(topicId, storeName),
    saveTopicMergedCsv: (topicId, payload) =>
      gapi.saveGeneralTopicMergedCsv(topicId, payload, storeName),
    parseQaCsvText: (text) => gapi.parseGeneralQaCsvText(text),
    createQaExtractJob: extractionDisabled,
    getQaExtractJob: extractionDisabled,
    importQaExtractJob: extractionDisabled,
  };
}

export default function GeneralKnowledgeWorkspace({
  active,
  storeName,
  onTopicsChanged,
}: GeneralKnowledgeWorkspaceProps) {
  // Rebuild the bound API client only when the store changes — avoids
  // recreating all its closures on every render.
  const api = useMemo(() => makeApi(storeName), [storeName]);
  const config: QaWorkspaceConfig = {
    sourceType: 'general',
    api,
    text: (_language, zh) => zh,
    disableAiQaExtraction: true,
  };
  return (
    <QaKnowledgeWorkspace
      active={active}
      language={storeName as never}
      onTopicsChanged={onTopicsChanged}
      config={config}
    />
  );
}
