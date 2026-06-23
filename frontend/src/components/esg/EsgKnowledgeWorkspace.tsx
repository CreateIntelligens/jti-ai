import * as esg from '../../services/api/esg';
import { createFixedAppWorkspace } from '../_shared/qaKnowledgeWorkspace/createFixedAppWorkspace';

// ESG 是「標準」固定庫工作區：與 general 相同，但停用圖片與 AI Q&A 抽取。
// 與 JTI 對稱，僅 api 來源與 sourceType 不同，故共用 factory 產生。
const EsgKnowledgeWorkspace = createFixedAppWorkspace({
  sourceType: 'esg',
  listKnowledgeFiles: esg.listEsgKnowledgeFiles,
  listTopicsAdmin: esg.listEsgTopicsAdmin,
  getKnowledgeFileContent: esg.getEsgKnowledgeFileContent,
  uploadKnowledgeFileWithTopic: esg.uploadEsgKnowledgeFileWithTopic,
  deleteKnowledgeFile: esg.deleteEsgKnowledgeFile,
  updateTopic: esg.updateEsgTopic,
  reorderTopics: esg.reorderEsgTopics,
  setCategoryHidden: esg.setEsgCategoryHidden,
  createTopic: esg.createEsgTopic,
  updateKnowledgeFileMetadata: esg.updateEsgKnowledgeFileMetadata,
  updateKnowledgeFileContent: esg.updateEsgKnowledgeFileContent,
  downloadKnowledgeFile: esg.downloadEsgKnowledgeFile,
  getTopicMergedCsv: esg.getEsgTopicMergedCsv,
  saveTopicMergedCsv: esg.saveEsgTopicMergedCsv,
  parseQaCsvText: esg.parseEsgQaCsvText,
});

export default EsgKnowledgeWorkspace;
