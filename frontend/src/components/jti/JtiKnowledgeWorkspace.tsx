import * as jti from '../../services/api/jti';
import { createFixedAppWorkspace } from '../_shared/qaKnowledgeWorkspace/createFixedAppWorkspace';

// JTI 是「標準」固定庫工作區：與 general 相同，但停用圖片與 AI Q&A 抽取。
// 與 ESG 對稱，僅 api 來源與 sourceType 不同，故共用 factory 產生。
const JtiKnowledgeWorkspace = createFixedAppWorkspace({
  sourceType: 'jti',
  listKnowledgeFiles: jti.listJtiKnowledgeFiles,
  listTopicsAdmin: jti.listJtiTopicsAdmin,
  getKnowledgeFileContent: jti.getJtiKnowledgeFileContent,
  uploadKnowledgeFileWithTopic: jti.uploadJtiKnowledgeFileWithTopic,
  deleteKnowledgeFile: jti.deleteJtiKnowledgeFile,
  updateTopic: jti.updateJtiTopic,
  reorderTopics: jti.reorderJtiTopics,
  setCategoryHidden: jti.setJtiCategoryHidden,
  createTopic: jti.createJtiTopic,
  updateKnowledgeFileMetadata: jti.updateJtiKnowledgeFileMetadata,
  updateKnowledgeFileContent: jti.updateJtiKnowledgeFileContent,
  downloadKnowledgeFile: jti.downloadJtiKnowledgeFile,
  getTopicMergedCsv: jti.getJtiTopicMergedCsv,
  saveTopicMergedCsv: jti.saveJtiTopicMergedCsv,
  parseQaCsvText: jti.parseJtiQaCsvText,
});

export default JtiKnowledgeWorkspace;
