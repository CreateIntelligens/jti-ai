import { describe, expect, it } from 'vitest';

import {
  MAX_UPLOAD_FILE_SIZE_BYTES,
  validateUploadFiles,
} from '../src/utils/uploadLimits';

describe('uploadLimits', () => {
  it('accepts files at the shared upload size limit', () => {
    expect(validateUploadFiles([
      { name: 'ok.txt', size: MAX_UPLOAD_FILE_SIZE_BYTES },
    ])).toBeNull();
  });

  it('rejects any file above the shared upload size limit', () => {
    expect(validateUploadFiles([
      { name: 'ok.txt', size: 100 },
      { name: 'large.txt', size: MAX_UPLOAD_FILE_SIZE_BYTES + 1 },
    ])).toBe('檔案大小不可超過 5 MB');
  });
});
