import { useEffect, useMemo, useState, type ComponentProps } from 'react';
import ChatArea from '../components/ChatArea';
import SuggestSidebar from '../components/general/SuggestSidebar';
import type { QaAdminCategory, QaCategory } from '../config/qaTopics';
import type { AppTarget, KnowledgeLanguage } from '../types';
import { listGeneralTopics } from '../services/api/general';
import { listJtiTopics } from '../services/api/jti';
import { listEsgTopics } from '../services/api/esg';
import { listHciotTopics } from '../services/api/hciot';
import '../styles/general/page.css';
import '../styles/general/suggest.css';

type ChatAreaProps = ComponentProps<typeof ChatArea>;

export type GeneralProps = ChatAreaProps & {
  storeName: string | null;
  // Managed apps (JTI/HCIoT/ESG) keep their 常見問題 in their own topic stores,
  // so the suggest sidebar must read each app's topics endpoint rather than the
  // per-store general topics. Undefined ⇒ a plain general store.
  appTarget?: AppTarget;
  appLanguage?: KnowledgeLanguage;
};

// Resolve the 常見問題 loader for the active knowledge base. Managed apps read
// their own topics endpoint (keyed by language); plain general stores read the
// per-store general topics (keyed by store_name).
function loadTopicsFor(
  appTarget: AppTarget | undefined,
  appLanguage: KnowledgeLanguage | undefined,
  storeName: string,
): Promise<{ categories: QaCategory[] | QaAdminCategory[] }> {
  const lang = appLanguage || 'zh';
  switch (appTarget) {
    case 'jti':
      return listJtiTopics(lang);
    case 'esg':
      return listEsgTopics(lang);
    case 'hciot':
      return listHciotTopics(lang);
    default:
      return listGeneralTopics(storeName);
  }
}

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

export default function General({ storeName, appTarget, appLanguage, ...chatProps }: GeneralProps) {
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
      setTopicsLoading(false);
      setTopicsError(false);
      setTopicsOpen(false);
      return () => { active = false; };
    }

    setTopicsLoading(true);
    setTopicsError(false);
    void loadTopicsFor(appTarget, appLanguage, storeName)
      .then((data) => {
        if (!active) return;
        const nextCategories = buildVisibleQaCategories(
          (data.categories || []) as QaAdminCategory[],
        );
        const firstCategory = nextCategories[0] || null;
        setCategories(nextCategories);
        setSelectedCategoryId(firstCategory?.id || null);
        setSelectedTopicId(firstCategory?.topics[0]?.id || null);
        // 設計稿：進對話檢視時常見問題側欄預設開啟（有常見問題才開）。
        setTopicsOpen(nextCategories.length > 0);
      })
      .catch((error) => {
        if (!active) return;
        console.error('General failed to load quick questions:', error);
        setCategories([]);
        setSelectedCategoryId(null);
        setSelectedTopicId(null);
        setTopicsError(true);
        setTopicsOpen(false);
      })
      .finally(() => {
        if (active) setTopicsLoading(false);
      });

    return () => { active = false; };
  }, [storeName, appTarget, appLanguage]);

  const allTopics = useMemo(
    () => categories.flatMap((category) => category.topics),
    [categories],
  );
  const quickPrompts = useMemo(
    () => Array.from(new Set(allTopics.flatMap((topic) => topic.questions))).slice(0, 6),
    [allTopics],
  );

  const selectQuestion = (question: string) => {
    if (chatProps.disabled || chatProps.loading) return;
    chatProps.onSendMessage(question);
    setTopicsOpen(false);
  };

  const suggestSidebar = topicsOpen ? (
    <SuggestSidebar
      categories={categories}
      selectedCategoryId={selectedCategoryId}
      selectedTopicId={selectedTopicId}
      onSelectCategory={(categoryId) => {
        const category = categories.find((item) => item.id === categoryId);
        setSelectedCategoryId(categoryId);
        setSelectedTopicId((category?.topics || allTopics)[0]?.id || null);
      }}
      onSelectTopic={(topicId) => setSelectedTopicId(topicId)}
      onSelectQuestion={selectQuestion}
      onClose={() => setTopicsOpen(false)}
      disabled={chatProps.disabled || chatProps.loading || topicsLoading}
    />
  ) : null;

  return (
    <div className="general-page">
      <ChatArea
        {...chatProps}
        onOpenTopics={() => setTopicsOpen((open) => !open)}
        topicsOpen={topicsOpen}
        topicsDisabled={!storeName || topicsLoading || topicsError || categories.length === 0}
        quickPrompts={quickPrompts}
        quickPromptsLoading={topicsLoading}
        quickPromptsMessage={topicsError ? '無法載入常見問題，仍可直接輸入問題。' : undefined}
        suggestSidebar={suggestSidebar}
      />
    </div>
  );
}
