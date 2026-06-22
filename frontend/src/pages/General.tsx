import { useEffect, useMemo, useState, type ComponentProps } from 'react';
import { ListChecks } from 'lucide-react';

import ChatArea from '../components/ChatArea';
import QaTopicGrid from '../components/_shared/QaTopicGrid';
import type { QaAdminCategory, QaCategory, QaTopic } from '../config/qaTopics';
import { listGeneralTopics } from '../services/api/general';
import '../styles/qaWorkspace/layout.css';
import '../styles/qaWorkspace/components.css';
import '../styles/qaWorkspace/components-topic.css';
import '../styles/general/page.css';

type ChatAreaProps = ComponentProps<typeof ChatArea>;

export type GeneralProps = ChatAreaProps & {
  storeName: string | null;
};

export function buildVisibleQaCategories(categories: QaAdminCategory[]): QaCategory[] {
  return categories.flatMap((category) => {
    if (category.hidden) return [];

    const topics = category.topics.flatMap((topic) => {
      if (topic.hidden) return [];
      const hiddenQuestions = new Set(topic.hidden_questions || []);
      const questions = topic.questions.filter((question) => !hiddenQuestions.has(question));
      return questions.length ? [{ ...topic, questions }] : [];
    });

    return topics.length ? [{ ...category, topics }] : [];
  });
}

export default function General({ storeName, ...chatProps }: GeneralProps) {
  const [categories, setCategories] = useState<QaCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [topicsError, setTopicsError] = useState(false);
  const [topicsOpen, setTopicsOpen] = useState(false);

  useEffect(() => {
    let active = true;

    if (!storeName) {
      setCategories([]);
      setSelectedCategoryId(null);
      setSelectedTopicId(null);
      setTopicsError(false);
      return () => { active = false; };
    }

    setTopicsLoading(true);
    setTopicsError(false);
    void listGeneralTopics(storeName)
      .then((data) => {
        if (!active) return;
        const nextCategories = buildVisibleQaCategories(
          (data.categories || []) as QaAdminCategory[],
        );
        const firstCategory = nextCategories[0] || null;
        setCategories(nextCategories);
        setSelectedCategoryId(firstCategory?.id || null);
        setSelectedTopicId(firstCategory?.topics[0]?.id || null);
      })
      .catch((error) => {
        if (!active) return;
        console.error('General failed to load quick questions:', error);
        setCategories([]);
        setSelectedCategoryId(null);
        setSelectedTopicId(null);
        setTopicsError(true);
      })
      .finally(() => {
        if (active) setTopicsLoading(false);
      });

    return () => { active = false; };
  }, [storeName]);

  const allTopics = useMemo(
    () => categories.flatMap((category) => category.topics),
    [categories],
  );
  const visibleTopics = useMemo(() => {
    if (!selectedCategoryId) return allTopics;
    return categories.find((category) => category.id === selectedCategoryId)?.topics || [];
  }, [allTopics, categories, selectedCategoryId]);

  const selectTopic = (topic: QaTopic) => {
    setSelectedTopicId(topic.id);
  };

  const selectQuestion = (question: string) => {
    if (chatProps.disabled || chatProps.loading) return;
    chatProps.onSendMessage(question);
    setTopicsOpen(false);
  };

  const disabledMessage = !storeName
    ? '請先選擇知識庫。'
    : topicsError
      ? '無法載入常用問題，請稍後再試。'
      : null;

  return (
    <div className="general-page">
      <button
        type="button"
        className="general-topic-toggle"
        onClick={() => setTopicsOpen((open) => !open)}
        aria-expanded={topicsOpen}
        aria-controls="general-topic-panel"
      >
        <ListChecks size={18} />
        常用問題
      </button>
      <div
        className={`general-topic-overlay${topicsOpen ? ' is-visible' : ''}`}
        onClick={() => setTopicsOpen(false)}
      />
      <div
        id="general-topic-panel"
        className={`general-topic-panel${topicsOpen ? ' is-open' : ''}`}
      >
        <QaTopicGrid
          topics={visibleTopics}
          categories={categories}
          disabled={chatProps.disabled || chatProps.loading || topicsLoading}
          disabledMessage={disabledMessage}
          heading="常用問題主題"
          allCategoriesLabel="全部分類"
          onSelect={selectTopic}
          onSelectQuestion={selectQuestion}
          selectedTopicId={selectedTopicId}
          selectedCategoryId={selectedCategoryId}
          onSelectCategory={(categoryId) => {
            const category = categories.find((item) => item.id === categoryId);
            setSelectedCategoryId(categoryId);
            setSelectedTopicId((category?.topics || allTopics)[0]?.id || null);
          }}
        />
      </div>
      <ChatArea {...chatProps} />
    </div>
  );
}
