import { useState, useCallback } from 'react';
import { Library, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';

export interface Citation {
  title: string;
  uri: string;
}

interface CitationsListProps {
  citations: Citation[];
  messageIndex: number;
}

export default function CitationsList({ citations, messageIndex }: CitationsListProps) {
  const [expanded, setExpanded] = useState(false);

  const toggle = useCallback(() => {
    setExpanded(prev => !prev);
  }, []);

  if (citations.length === 0) return null;

  return (
    <div className="citations-container">
      <button
        onClick={toggle}
        className={`citations-toggle ${expanded ? 'active' : ''}`}
        aria-expanded={expanded}
      >
        <Library className="citations-icon" size={14} />
        <span className="citations-label">參考資料 ({citations.length})</span>
        {expanded ? (
          <ChevronUp className="citations-chevron" size={14} />
        ) : (
          <ChevronDown className="citations-chevron" size={14} />
        )}
      </button>
      {expanded && (
        <div className="citations-list">
          {citations.map((cit, i) => {
            const title = cit.title || cit.uri || '參考資料';
            return cit.uri ? (
              <a
                key={`${messageIndex}-cit-${i}`}
                href={cit.uri}
                target="_blank"
                rel="noreferrer"
                className="citation-badge link"
                title={title}
              >
                <span className="citation-number">[{i + 1}]</span>
                <span className="citation-title">{title}</span>
                <ExternalLink size={12} className="citation-external-icon" />
              </a>
            ) : (
              <span key={`${messageIndex}-cit-${i}`} className="citation-badge" title={title}>
                <span className="citation-number">[{i + 1}]</span>
                <span className="citation-title">{title}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
