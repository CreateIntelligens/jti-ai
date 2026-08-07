import { useMemo } from 'react';
import * as gapi from '../../services/api/general';
import QaKnowledgeWorkspace, {
  type QaWorkspaceApiClient,
  type QaWorkspaceConfig,
} from '../_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';
// Shared QA workspace styles (originally authored under hciot/, app-wide CSS).
import '../../styles/qaWorkspace/layout.css';
import '../../styles/qaWorkspace/workspace.css';
import '../../styles/qaWorkspace/workspace-table.css';
import '../../styles/qaWorkspace/workspace-images.css';
import '../../styles/qaWorkspace/workspace-upload.css';
import '../../styles/qaWorkspace/workspace-upload-images.css';
import '../../styles/qaWorkspace/workspace-upload-enhancements.css';
import '../../styles/qaWorkspace/workspace-upload-preview.css';
import '../../styles/qaWorkspace/workspace-upload-edit.css';

interface GeneralKnowledgeWorkspaceProps {
  active: boolean;
  storeName: string;
  onTopicsChanged?: () => Promise<void> | void;
}

// Build a workspace API client bound to one general store. The shared workspace
// passes a `language` arg into every method; general ignores it (the store is
// fixed by closure) and routes by store_name instead.
function makeApi(storeName: string): QaWorkspaceApiClient {
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
  };
}

export default function GeneralKnowledgeWorkspace({
  active,
  storeName,
  onTopicsChanged,
}: GeneralKnowledgeWorkspaceProps) {
  // Rebuild the bound API client and workspace config only when the store
  // changes — avoids recreating closures (including resolveImageUrl) on every render.
  const api = useMemo(() => makeApi(storeName), [storeName]);

  const config = useMemo<QaWorkspaceConfig>(() => ({
    sourceType: 'general',
    api,
    text: (_language, zh) => zh,
    // general 動態知識庫的 Q&A 也會帶圖與參考連結（醫療衛教等情境），
    // 因此開放圖片 (IMG) / 網址 (URL) 欄位；沒有圖的列留白即可。
    disableImages: false,
    resolveImageUrl: (imageId) => gapi.getGeneralImageUrl(storeName, imageId),
  }), [api, storeName]);
  return (
    <QaKnowledgeWorkspace
      active={active}
      language={storeName as never}
      onTopicsChanged={onTopicsChanged}
      config={config}
    />
  );
}
