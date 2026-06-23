import type { QaLanguage } from '../../../config/qaTopics';
import reindexRag, { getReindexStatus, type RagSourceType } from '../../../services/api/general';
import QaKnowledgeWorkspace, {
  type QaWorkspaceApiClient,
  type QaWorkspaceConfig,
} from './QaKnowledgeWorkspace';
// Shared QA workspace styles (app-wide CSS, originally authored under hciot/).
import '../../../styles/qaWorkspace/layout.css';
import '../../../styles/qaWorkspace/workspace.css';
import '../../../styles/qaWorkspace/workspace-table.css';
import '../../../styles/qaWorkspace/workspace-upload.css';
import '../../../styles/qaWorkspace/workspace-upload-enhancements.css';
import '../../../styles/qaWorkspace/workspace-upload-preview.css';
import '../../../styles/qaWorkspace/workspace-upload-edit.css';

export interface FixedAppWorkspaceProps {
  active: boolean;
  language: QaLanguage;
  onTopicsChanged?: () => Promise<void> | void;
}

// The per-app api functions a "standard" fixed-app workspace actually consumes.
// jti and esg supply these from their own api modules (jti's file CRUD is hand
// written; esg's comes from createQaKnowledgeApi) — the factory does not care
// where they come from, only that they match this shape.
type FixedAppWorkspaceFns = Pick<
  QaWorkspaceApiClient,
  | 'listKnowledgeFiles'
  | 'listTopicsAdmin'
  | 'getKnowledgeFileContent'
  | 'uploadKnowledgeFileWithTopic'
  | 'deleteKnowledgeFile'
  | 'updateTopic'
  | 'reorderTopics'
  | 'setCategoryHidden'
  | 'createTopic'
  | 'updateKnowledgeFileMetadata'
  | 'updateKnowledgeFileContent'
  | 'downloadKnowledgeFile'
  | 'getTopicMergedCsv'
  | 'saveTopicMergedCsv'
  | 'parseQaCsvText'
>;

export interface FixedAppWorkspaceOptions extends FixedAppWorkspaceFns {
  /** RAG source type; also the upper-cased app label used in disabled-feature errors. */
  sourceType: string;
}

/**
 * Build a "standard" fixed-app knowledge-workspace component (jti / esg):
 * identical to general, but with image support and AI Q&A extraction fully
 * disabled (images are an HCIoT-only feature). Image methods are no-ops
 * returning empty results so the shared workspace never hits the network for
 * them; extraction methods reject defensively. jti and esg are identical apart
 * from their api functions and `sourceType`, so they are produced here rather
 * than copy-pasted.
 */
export function createFixedAppWorkspace({ sourceType, ...fns }: FixedAppWorkspaceOptions) {
  const appLabel = sourceType.toUpperCase();
  const asRag = (s: string) => s as RagSourceType;

  const api: QaWorkspaceApiClient = {
    ...fns,
    listImages: () => Promise.resolve({ images: [] }),
    getReindexStatus: (s) => getReindexStatus(asRag(s)),
    reindex: (s) => reindexRag(asRag(s)),
    uploadImage: () => Promise.reject(new Error(`Image upload is disabled for ${appLabel}`)),
    deleteImage: () => Promise.reject(new Error(`Image management is disabled for ${appLabel}`)),
    deleteUnusedImages: () =>
      Promise.resolve({ deleted_count: 0, deleted_image_ids: [] as string[] }),
    createQaExtractJob: () => Promise.reject(new Error(`QA extraction is disabled for ${appLabel}`)),
    getQaExtractJob: () => Promise.reject(new Error(`QA extraction is disabled for ${appLabel}`)),
    importQaExtractJob: () => Promise.reject(new Error(`QA extraction is disabled for ${appLabel}`)),
  };

  const config: QaWorkspaceConfig = {
    sourceType,
    api,
    text: (_language, zh) => zh,
    disableAiQaExtraction: true,
    disableImages: true,
  };

  return function FixedAppKnowledgeWorkspace(props: FixedAppWorkspaceProps) {
    return <QaKnowledgeWorkspace {...props} config={config} />;
  };
}
