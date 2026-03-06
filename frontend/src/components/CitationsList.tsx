import { useState, useCallback } from 'react';

export interface Citation {
  title: string;
  uri: string;
}

interface CitationsListProps {
  citations: Citation[];
  messageIndex: number;
}

const BADGE_CLASS =
  'inline-block px-2 py-0.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded text-[11px] text-white/70 transition-colors truncate max-w-[200px]';

export default function CitationsList({ citations, messageIndex }: CitationsListProps) {
  const [expanded, setExpanded] = useState(false);

  const toggle = useCallback(() => {
    setExpanded(prev => !prev);
  }, []);

  if (citations.length === 0) return null;

  return (
    <div className="citations-list mt-2 border-t border-white/10 pt-2">
      <button
        onClick={toggle}
        className="text-xs text-white/50 hover:text-white/70 flex items-center gap-1 transition-colors bg-transparent border-0 p-0 cursor-pointer"
      >
        <span>📚</span>
        <span>參考資料 ({citations.length})</span>
        <span>{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="flex flex-wrap gap-1 mt-1">
          {citations.map((cit, i) => {
            const title = cit.title || cit.uri || '參考資料';
            return cit.uri ? (
              <a
                key={`${messageIndex}-cit-${i}`}
                href={cit.uri}
                target="_blank"
                rel="noreferrer"
                className={`${BADGE_CLASS} no-underline`}
                title={title}
              >
                [{i + 1}] {title}
              </a>
            ) : (
              <span key={`${messageIndex}-cit-${i}`} className={BADGE_CLASS} title={title}>
                [{i + 1}] {title}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
