import type { HciotLanguage } from '../../config/hciotTopics';
import * as api from '../../services/api';
import reindexRag, { getReindexStatus, type RagSourceType } from '../../services/api/general';
import QaKnowledgeWorkspace, {
  type QaWorkspaceApiClient,
  type QaWorkspaceConfig,
} from '../_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';

interface HciotKnowledgeWorkspaceProps {
  active: boolean;
  language: HciotLanguage;
  onTopicsChanged?: () => Promise<void> | void;
}

function toRagSourceType(sourceType: string): RagSourceType {
  return sourceType as RagSourceType;
}

const hciotQaWorkspaceApi: QaWorkspaceApiClient = {
  listKnowledgeFiles: api.listHciotKnowledgeFiles,
  listTopicsAdmin: api.listHciotTopicsAdmin,
  listImages: api.listHciotImages,
  getReindexStatus: (sourceType) => getReindexStatus(toRagSourceType(sourceType)),
  reindex: (sourceType) => reindexRag(toRagSourceType(sourceType)),
  getKnowledgeFileContent: api.getHciotKnowledgeFileContent,
  uploadKnowledgeFileWithTopic: api.uploadHciotKnowledgeFileWithTopic,
  deleteKnowledgeFile: api.deleteHciotKnowledgeFile,
  updateTopic: api.updateHciotTopic,
  reorderTopics: api.reorderHciotTopics,
  setCategoryHidden: api.setHciotCategoryHidden,
  uploadImage: api.uploadHciotImage,
  deleteImage: api.deleteHciotImage,
  deleteUnusedImages: api.deleteUnusedHciotImages,
  createTopic: api.createHciotTopic,
  updateKnowledgeFileMetadata: api.updateHciotKnowledgeFileMetadata,
  updateKnowledgeFileContent: api.updateHciotKnowledgeFileContent,
  downloadKnowledgeFile: api.downloadHciotKnowledgeFile,
  getTopicMergedCsv: api.getHciotTopicMergedCsv,
  saveTopicMergedCsv: api.saveHciotTopicMergedCsv,
  createQaExtractJob: api.createQaExtractJob,
  parseQaCsvText: api.parseQaCsvText,
  getQaExtractJob: api.getQaExtractJob,
  importQaExtractJob: api.importQaExtractJob,
};

const hciotQaWorkspaceConfig: QaWorkspaceConfig = {
  sourceType: 'hciot',
  api: hciotQaWorkspaceApi,
  text: (_language, zh) => zh,
  // HCIoT saves pasted text / uploaded docs directly (chunked by RAG backfill)
  // instead of using AI Q&A extraction. The extraction capability stays intact
  // for other sub-apps.
  disableAiQaExtraction: true,
};

export default function HciotKnowledgeWorkspace(props: HciotKnowledgeWorkspaceProps) {
  return <QaKnowledgeWorkspace {...props} config={hciotQaWorkspaceConfig} />;
}
