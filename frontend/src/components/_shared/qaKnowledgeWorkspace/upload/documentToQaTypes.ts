import { MAX_UPLOAD_FILE_SIZE_BYTES } from '../../../../utils/uploadLimits';

export type DocumentSourceMode = 'file' | 'text';
export type DocumentToQaStatus = 'idle' | 'uploading' | 'extracting' | 'preview' | 'importing' | 'success' | 'error';

export const POLLING_INTERVAL_MS = 1500;
export const TIMEOUT_MS = 5 * 60 * 1000;
export const MAX_TEXT_LENGTH = 30000;
export const MAX_FILE_SIZE_BYTES = MAX_UPLOAD_FILE_SIZE_BYTES;
export const SUPPORTED_EXTS = ['docx', 'txt', 'md', 'csv', 'xlsx'];

export interface DocFileItem {
  file: File;
}
