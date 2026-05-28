import { useEffect, useRef, useState } from 'react';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';
import { getErrorMessage } from '../topicUtils';

export interface UseReindexOptions {
  api: QaWorkspaceApiClient;
  sourceType: string;
  refreshWorkspace: () => Promise<void>;
  showStatus: (message: string) => void;
  text: (zh: string, en: string) => string;
}

export function useReindex({
  api,
  sourceType,
  refreshWorkspace,
  showStatus,
  text,
}: UseReindexOptions) {
  const reindexTimerRef = useRef<number | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const clearReindexTimer = () => {
    if (reindexTimerRef.current !== null) {
      window.clearInterval(reindexTimerRef.current);
      reindexTimerRef.current = null;
    }
  };

  useEffect(() => () => {
    clearReindexTimer();
  }, []);

  const pollReindexStatus = (source: string) => {
    clearReindexTimer();
    let attempts = 0;
    const maxAttempts = 60; // Max 3 minutes
    reindexTimerRef.current = window.setInterval(async () => {
      attempts += 1;
      try {
        const res = await api.getReindexStatus(source);
        if (!res.reindexing || attempts >= maxAttempts) {
          clearReindexTimer();
          setReindexing(false);
          if (!res.reindexing) {
            showStatus(text('重新索引已完成', 'Reindexing completed'));
            void refreshWorkspace();
          }
        }
      } catch (error) {
        console.error('Failed to query reindex status:', error);
      }
    }, 3000);
  };

  const handleReindex = async () => {
    if (reindexing) return;
    if (!window.confirm(text(
      '確定要重新索引嗎？這將會暫停服務約 1 分鐘。',
      'Are you sure you want to reindex? This will pause service for about 1 minute.',
    ))) {
      return;
    }

    setReindexing(true);
    try {
      await api.reindex(sourceType);
      showStatus(text('重新索引已開始', 'Reindexing started'));
      pollReindexStatus(sourceType);
    } catch (error) {
      console.error('Failed to reindex RAG:', error);
      alert(getErrorMessage(error));
      setReindexing(false);
    }
  };

  return {
    reindexing,
    setReindexing,
    pollReindexStatus,
    handleReindex,
  };
}
