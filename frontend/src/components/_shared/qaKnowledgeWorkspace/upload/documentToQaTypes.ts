import { MAX_UPLOAD_FILE_SIZE_BYTES } from '../../../../utils/uploadLimits';

export type DocumentSourceMode = 'file' | 'text';
export type DocumentToQaStatus = 'idle' | 'uploading' | 'preview' | 'importing' | 'success' | 'error';

export const MAX_TEXT_LENGTH = 30000;
export const MAX_FILE_SIZE_BYTES = MAX_UPLOAD_FILE_SIZE_BYTES;
export const SUPPORTED_EXTS = ['docx', 'txt', 'md', 'csv', 'xlsx'];

export interface DocFileItem {
  file: File;
}
