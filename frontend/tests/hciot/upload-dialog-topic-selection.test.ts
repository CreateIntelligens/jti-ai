import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildUploadTopicOptions,
  isUploadTopicSelectDisabled,
  readSavedTopicSelection,
} from '../../src/components/_shared/qaKnowledgeWorkspace/upload/UploadDialog';
import { NEW_VALUE } from '../../src/components/_shared/qaKnowledgeWorkspace/topicUtils';

describe('UploadDialog topic selection', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('starts an empty topic list in new category and new topic mode', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    });

    expect(readSavedTopicSelection([])).toEqual({
      categoryId: NEW_VALUE,
      topicId: NEW_VALUE,
    });
  });

  it('keeps new topic creation available while adding a new category', () => {
    expect(isUploadTopicSelectDisabled(NEW_VALUE)).toBe(false);
    expect(buildUploadTopicOptions(NEW_VALUE, [], 'en')).toContainEqual({
      value: NEW_VALUE,
      label: '＋ 新增主題',
    });
  });
});
