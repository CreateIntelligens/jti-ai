import type { TopicLabels } from '../topicUtils';

export type FileStatus = 'pending' | 'uploading' | 'done' | 'error';

export interface ResolvedUploadTopic {
  fullTopicId: string;
  labels: TopicLabels;
}

export interface QARow {
  index?: string;
  q: string;
  a: string;
  img?: string;
  url?: string;
  pendingImageFile?: File | null;
  pendingImageName?: string;
  imgStatus?: FileStatus;
  imgError?: string;
  // Whether this question shows in the topic's preset-question chips.
  // Unchecked rows still upload and still enter the RAG knowledge base — only
  // the chip is hidden (via the topic's hidden_questions field).
  visible: boolean;
}

export interface FileItem {
  file: File;
  status: FileStatus;
  error?: string;
  isDuplicate?: boolean;
}

export interface ImageItem {
  file: File;
  imageId: string;
  status: FileStatus;
  error?: string;
}

export function createEmptyRow(): QARow {
  return { q: '', a: '', img: '', url: '', imgStatus: 'pending', visible: true };
}

export function clearRowImageState(row: QARow): QARow {
  return {
    ...row,
    img: '',
    pendingImageFile: undefined,
    pendingImageName: undefined,
    imgStatus: 'pending',
    imgError: undefined,
  };
}

export function applyExistingRowImage(row: QARow, imageId: string): QARow {
  return {
    ...clearRowImageState(row),
    img: imageId,
    imgStatus: 'done',
  };
}

export function buildCsvBlob(rows: QARow[]): Blob {
  const lines = ['q,a,img,url'];
  rows.forEach((row) => {
    const q = row.q.replace(/"/g, '""');
    const a = row.a.replace(/"/g, '""');
    const img = (row.img || '').replace(/"/g, '""');
    const url = (row.url || '').replace(/"/g, '""');
    lines.push(`"${q}","${a}","${img}","${url}"`);
  });
  return new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
}
