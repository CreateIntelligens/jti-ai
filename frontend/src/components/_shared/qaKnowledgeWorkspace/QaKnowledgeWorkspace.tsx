import { useEffect, useMemo, useState } from 'react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import type {
  HciotImage,
  HciotKnowledgeFile,
  HciotMergedCsvRow,
  HciotQaPair,
  HciotTopicCategory,
  QaExtractJobResponse,
  QaImportResponse,
} from '../../../services/api/hciot';
import ExplorerSidebar from './explorer/ExplorerSidebar';
import VisibilityOrderModal from './explorer/VisibilityOrderModal';
import FileDetailPane from './detail/FileDetailPane';
import MergedCsvPane from './detail/MergedCsvPane';
import UploadDialog from './upload/UploadDialog';
import ImageDetailPane from './detail/ImageDetailPane';
import {
  splitTopicId,
  type TopicLabels,
} from './topicUtils';
import { useEscapeKey } from '../../../hooks/useEscapeKey';
import { getCurrentPathLabel } from './explorer/explorerTree';

// Custom Hooks
import { useWorkspaceData } from './hooks/useWorkspaceData';
import { useFileEditor } from './hooks/useFileEditor';
import { useReindex } from './hooks/useReindex';
import { useExplorerTree } from './hooks/useExplorerTree';
import { useImageManagement } from './hooks/useImageManagement';
import { useTopicMutations } from './hooks/useTopicMutations';

export type QaWorkspaceSourceType = 'hciot' | 'jti' | string;

type KnowledgeFileContentResponse = {
  content?: string | null;
  editable?: boolean;
  message?: string | null;
};

type TopicUpdatePayload = {
  labels?: string;
  category_labels?: string;
  questions?: string[];
  hidden_questions?: string[];
  hidden?: boolean;
};

type KnowledgeMetadataPayload = {
  topic_id?: string | null;
  category_label?: string | null;
  topic_label?: string | null;
};

type MergedCsvResponse = {
  rows: HciotMergedCsvRow[];
  source_files: string[];
};

export interface QaWorkspaceApiClient {
  listKnowledgeFiles(language: HciotLanguage): Promise<{ files: HciotKnowledgeFile[] }>;
  listTopicsAdmin(language: HciotLanguage): Promise<{ categories: HciotTopicCategory[] }>;
  listImages(): Promise<{ images: HciotImage[] }>;
  getReindexStatus(sourceType: QaWorkspaceSourceType): Promise<{ reindexing: boolean }>;
  reindex(sourceType: QaWorkspaceSourceType): Promise<unknown>;
  getKnowledgeFileContent(filename: string, language: HciotLanguage): Promise<KnowledgeFileContentResponse>;
  uploadKnowledgeFileWithTopic(opts: {
    language: HciotLanguage;
    file: File;
    categoryId?: string;
    topicId?: string;
    categoryLabel?: string;
    topicLabel?: string;
    hiddenQuestions?: string[];
  }): Promise<HciotKnowledgeFile & { uploaded_count?: number }>;
  deleteKnowledgeFile(filename: string, language: HciotLanguage): Promise<void>;
  updateTopic(topicId: string, data: TopicUpdatePayload, language: HciotLanguage): Promise<Record<string, unknown>>;
  reorderTopics(topicIds: string[], language: HciotLanguage): Promise<{ updated: number }>;
  setCategoryHidden(categoryId: string, hidden: boolean, language: HciotLanguage): Promise<Record<string, unknown>>;
  uploadImage(file: File, imageId?: string): Promise<HciotImage>;
  deleteImage(imageId: string): Promise<void>;
  deleteUnusedImages(): Promise<{ deleted_count: number; deleted_image_ids: string[] }>;
  createTopic(topicId: string, label: string, categoryLabel: string, questions: string[] | undefined, language: HciotLanguage): Promise<Record<string, unknown>>;
  updateKnowledgeFileMetadata(filename: string, metadata: KnowledgeMetadataPayload, language: HciotLanguage): Promise<HciotKnowledgeFile & { topic_synced: boolean }>;
  updateKnowledgeFileContent(filename: string, content: string, language: HciotLanguage): Promise<{ message: string; synced: boolean; topic_synced: boolean }>;
  downloadKnowledgeFile(filename: string, language: HciotLanguage): void;
  getTopicMergedCsv(topicId: string, language: HciotLanguage): Promise<MergedCsvResponse>;
  createQaExtractJob(
    language: HciotLanguage,
    source: { file: File } | { text: string },
    categoryId: string,
    topicId: string,
    categoryLabel: string,
    topicLabel: string,
  ): Promise<{ job_id: string; status: string }>;
  parseQaCsvText(text: string): Promise<{ parsed: boolean; qa_pairs: HciotQaPair[] }>;
  getQaExtractJob(jobId: string): Promise<QaExtractJobResponse>;
  importQaExtractJob(
    jobId: string,
    language: HciotLanguage,
    qaPairs: HciotQaPair[],
    hiddenQuestions?: string[],
  ): Promise<QaImportResponse>;
}

export interface QaWorkspaceConfig {
  sourceType: QaWorkspaceSourceType;
  api: QaWorkspaceApiClient;
  text?: (language: HciotLanguage, zh: string, en: string) => string;
}

interface QaKnowledgeWorkspaceProps {
  active: boolean;
  language: HciotLanguage;
  onTopicsChanged?: () => Promise<void> | void;
  config: QaWorkspaceConfig;
}

function getLocalizedText(_language: HciotLanguage, zh: string, _en: string): string {
  return zh;
}

export default function QaKnowledgeWorkspace({
  active,
  language,
  onTopicsChanged,
  config,
}: QaKnowledgeWorkspaceProps) {
  const [qaDialogOpen, setQaDialogOpen] = useState(false);
  const [manageDialogOpen, setManageDialogOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [savingManagement, setSavingManagement] = useState(false);

  const api = config.api;
  const text = (zh: string, en: string) => (config.text || getLocalizedText)(language, zh, en);

  // 1. Workspace Data Hook
  const workspaceData = useWorkspaceData({
    api,
    language,
    onTopicsChanged,
    text,
  });

  // 2. Explorer Tree Hook
  const explorerTree = useExplorerTree({
    files: workspaceData.files,
    categories: workspaceData.categories,
    language,
    images: workspaceData.images,
  });

  // 3. File Editor Hook
  const fileEditor = useFileEditor({
    api,
    language,
    selectedFileName: workspaceData.selectedFileName,
    setSelectedFileName: workspaceData.setSelectedFileName,
    setSelectedImageName: workspaceData.setSelectedImageName,
    setSelectedMergedTopicId: workspaceData.setSelectedMergedTopicId,
    selectedFile: workspaceData.selectedFile,
    categories: workspaceData.categories,
    setFiles: workspaceData.setFiles,
    refreshWorkspaceAfterTopicChange: workspaceData.refreshWorkspaceAfterTopicChange,
    showStatus: workspaceData.showStatus,
    ensureSelectedPathExpanded: explorerTree.ensureSelectedPathExpanded,
    text,
  });

  // 4. Reindex Hook
  const reindexData = useReindex({
    api,
    sourceType: config.sourceType,
    refreshWorkspace: workspaceData.refreshWorkspace,
    showStatus: workspaceData.showStatus,
    text,
  });

  // 5. Image Management Hook
  const imageManagement = useImageManagement({
    api,
    selectedImage: workspaceData.selectedImage,
    selectedImageName: workspaceData.selectedImageName,
    setSelectedImageName: workspaceData.setSelectedImageName,
    unusedImageCount: workspaceData.unusedImageCount,
    refreshWorkspace: workspaceData.refreshWorkspace,
    completeUpload: workspaceData.completeUpload,
    showStatus: workspaceData.showStatus,
    text,
  });

  // 6. Topic Mutations Hook
  const topicMutations = useTopicMutations({
    api,
    language,
    files: workspaceData.files,
    categories: workspaceData.categories,
    draft: fileEditor.draft,
    setDraft: fileEditor.setDraft,
    patchDraft: fileEditor.patchDraft,
    selectedFileName: workspaceData.selectedFileName,
    setSelectedFileName: workspaceData.setSelectedFileName,
    selectedMergedTopicId: workspaceData.selectedMergedTopicId,
    setSelectedMergedTopicId: workspaceData.setSelectedMergedTopicId,
    refreshWorkspaceAfterTopicChange: workspaceData.refreshWorkspaceAfterTopicChange,
    showStatus: workspaceData.showStatus,
    discardChanges: fileEditor.discardChanges,
    text,
  });

  // Derived deleting state
  const deleting = fileEditor.deleting || imageManagement.deleting || topicMutations.deletingTopic;

  // Sync selections and workspace data loading/checks on active & language updates
  useEffect(() => {
    workspaceData.setSelectedFileName(null);
    workspaceData.setSelectedImageName(null);
    workspaceData.setSelectedMergedTopicId(null);
  }, [language]);

  useEffect(() => {
    if (!active) {
      return;
    }
    void workspaceData.refreshWorkspace();

    // Check if a reindex is already in progress when the workspace is activated
    api.getReindexStatus(config.sourceType)
      .then((res) => {
        if (res.reindexing) {
          reindexData.setReindexing(true);
          reindexData.pollReindexStatus(config.sourceType);
        }
      })
      .catch((err) => {
        console.error('Failed to check initial reindex status:', err);
      });
  }, [active, language]);

  const currentPathLabel = useMemo(
    () => getCurrentPathLabel(workspaceData.selectedFile, language),
    [language, workspaceData.selectedFile],
  );

  const sidebarExpanded = !explorerTree.sidebarCollapsed || explorerTree.sidebarHoverExpanded;

  const handleSelectImage = (fileName: string) => {
    if (!fileEditor.discardChanges()) return;
    fileEditor.selectWorkspaceItem({ imageName: fileName });
  };

  const handleSelectMergedCsv = (topicId: string) => {
    if (!fileEditor.discardChanges()) return;
    fileEditor.selectWorkspaceItem({ mergedTopicId: topicId });
  };

  const uploadFileWithTopic = async (
    file: File,
    topicId: string | null,
    labels: TopicLabels | null,
    hiddenQuestions?: string[],
  ) => {
    if (!topicId) {
      throw new Error("Topic ID is required.");
    }
    const { categoryId, topicSlug } = splitTopicId(topicId);
    return api.uploadKnowledgeFileWithTopic({
      language,
      file,
      categoryId: categoryId || undefined,
      topicId: topicSlug || undefined,
      categoryLabel: labels?.categoryLabel || undefined,
      topicLabel: labels?.topicLabel || undefined,
      hiddenQuestions,
    });
  };

  const handleUploadComplete = async (
    firstUploadedFileName: string | null,
    count: number,
    topicId?: string | null,
  ) => {
    await workspaceData.completeUpload(firstUploadedFileName, text(
      `已上傳 ${count} 個檔案`,
      `Uploaded ${count} file(s)`,
    ), topicId);
  };

  const handleQASubmit = async (
    file: File,
    topicId: string,
    labels: TopicLabels,
    hiddenQuestions: string[],
  ): Promise<{ name: string; uploaded_count: number }> => {
    setUploading(true);
    try {
      const response = await uploadFileWithTopic(file, topicId, labels, hiddenQuestions);
      return { name: response.name, uploaded_count: response.uploaded_count ?? 1 };
    } finally {
      setUploading(false);
    }
  };

  const handleSaveManagement = async (
    nextCategories: HciotTopicCategory[],
    changes: {
      categoryHidden: Array<{ categoryId: string; hidden: boolean }>;
      topicHidden: Array<{ topicId: string; hidden: boolean }>;
    },
  ) => {
    setSavingManagement(true);
    try {
      const topicIds = nextCategories.flatMap((category) => category.topics.map((topic) => topic.id));
      await Promise.all([
        api.reorderTopics(topicIds, language),
        ...changes.categoryHidden.map((item) =>
          api.setCategoryHidden(item.categoryId, item.hidden, language)
        ),
        ...changes.topicHidden.map((item) =>
          api.updateTopic(item.topicId, { hidden: item.hidden }, language)
        ),
      ]);
      setManageDialogOpen(false);
      await workspaceData.refreshWorkspaceAfterTopicChange();
      workspaceData.showStatus(text('管理設定已更新', 'Management settings updated'));
    } finally {
      setSavingManagement(false);
    }
  };

  const hasSelection = !!(workspaceData.selectedFileName || workspaceData.selectedImageName || workspaceData.selectedMergedTopicId);
  useEscapeKey(() => { if (fileEditor.discardChanges()) fileEditor.selectWorkspaceItem({}); }, hasSelection);

  return (
    <section
      className={`qa-workspace${active ? ' is-active' : ''}${sidebarExpanded ? ' is-sidebar-expanded' : ''}`}
    >
      <ExplorerSidebar
        sidebarCollapsed={explorerTree.sidebarCollapsed}
        loadingWorkspace={workspaceData.loadingWorkspace}
        searchQuery={explorerTree.searchQuery}
        deferredSearchQuery={explorerTree.deferredSearchQuery}
        selectedFileName={workspaceData.selectedFileName}
        selectedImageName={workspaceData.selectedImageName}
        visibleRows={explorerTree.visibleRows}
        visibleExpandedKeys={explorerTree.visibleExpandedKeys}
        onMouseEnter={explorerTree.handleSidebarMouseEnter}
        onMouseLeave={explorerTree.handleSidebarMouseLeave}
        onToggleSidebar={explorerTree.handleToggleSidebar}
        onSearchChange={explorerTree.setSearchQuery}
        onToggleExpanded={explorerTree.toggleExpanded}
        selectedMergedTopicId={workspaceData.selectedMergedTopicId}
        onSelectFile={fileEditor.handleSelectFile}
        onSelectImage={handleSelectImage}
        onSelectMergedCsv={handleSelectMergedCsv}
        onOpenUploadDialog={() => setQaDialogOpen(true)}
        onOpenManageDialog={() => setManageDialogOpen(true)}
        onDeleteTopic={topicMutations.handleDeleteTopic}
        onReindex={reindexData.handleReindex}
        reindexing={reindexData.reindexing}
        renamingKey={topicMutations.renamingKey}
        renaming={topicMutations.renaming}
        onStartRename={topicMutations.handleStartRename}
        onCommitRename={topicMutations.handleCommitRename}
        onCancelRename={topicMutations.handleCancelRename}
        onReorder={topicMutations.handleReorder}
      />

      <VisibilityOrderModal
        open={manageDialogOpen}
        categories={workspaceData.categories}
        saving={savingManagement}
        onClose={() => setManageDialogOpen(false)}
        onSave={handleSaveManagement}
      />

      <UploadDialog
        open={qaDialogOpen}
        language={language}
        categories={workspaceData.categories}
        availableImages={workspaceData.images}
        uploading={uploading}
        onClose={() => setQaDialogOpen(false)}
        onUploadFile={uploadFileWithTopic}
        onUploadComplete={handleUploadComplete}
        onSubmitQA={handleQASubmit}
        api={api}
        onUploadImage={api.uploadImage}
        onDeleteImage={api.deleteImage}
        onUploadImageComplete={imageManagement.handleUploadImageComplete}
      />

      {workspaceData.selectedImageName ? (
        <ImageDetailPane
          language={language}
          selectedImage={workspaceData.selectedImage}
          deleting={deleting}
          cleaningUnused={imageManagement.cleaningUnusedImages}
          unusedImageCount={workspaceData.unusedImageCount}
          onDelete={() => void imageManagement.handleDeleteImage()}
          onCleanupUnused={() => void imageManagement.handleCleanupUnusedImages()}
        />
      ) : workspaceData.selectedMergedTopicId ? (
        <MergedCsvPane
          topicId={workspaceData.selectedMergedTopicId}
          topicLabel={workspaceData.selectedMergedLabel}
          language={language}
          availableImages={workspaceData.images}
          statusMessage={workspaceData.statusMessage}
          hiddenQuestions={workspaceData.selectedMergedTopic?.hidden_questions}
          refreshKey={workspaceData.topicRefreshKey}
          api={api}
          onRefreshWorkspace={() => workspaceData.refreshWorkspaceAfterTopicChange()}
          onUploadImage={api.uploadImage}
          onDeleteImage={api.deleteImage}
          onDeleteTopic={topicMutations.handleDeleteTopic}
        />
      ) : (
        <FileDetailPane
          language={language}
          state={{
            selectedFile: workspaceData.selectedFile,
            currentPathLabel,
            statusMessage: workspaceData.statusMessage,
            deleting,
            saving: fileEditor.saving,
            uploading,
            hasUnsavedChanges: fileEditor.hasUnsavedChanges,
            draft: fileEditor.draft,
            fileEditable: fileEditor.fileEditable,
            loadingContent: fileEditor.loadingContent,
            contentMessage: fileEditor.contentMessage,
            editorText: fileEditor.editorText,
          }}
          actions={{
            onDownload: () => {
              if (workspaceData.selectedFile) api.downloadKnowledgeFile(workspaceData.selectedFile.name, language);
            },
            onDelete: () => { void fileEditor.handleDeleteFile(); },
            onSave: () => { void fileEditor.handleSave(); },
            onCategoryChange: topicMutations.handleCategoryChange,
            onTopicChange: topicMutations.handleTopicChange,
            onDraftChange: fileEditor.patchDraft,
            onEditorTextChange: fileEditor.setEditorText,
          }}
          categoryOptions={topicMutations.categoryOptions}
          topicOptions={topicMutations.topicOptions}
        />
      )}
    </section>
  );
}
