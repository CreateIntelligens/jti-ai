import { useState, useCallback } from 'react';
import { Library, ChevronDown, ChevronUp } from 'lucide-react';

export interface Citation {
  title: string;
  uri: string;
  text?: string;
}

interface CitationsListProps {
  citations: Citation[];
  messageIndex: number;
}

export default function CitationsList({ citations, messageIndex }: CitationsListProps) {
  const [expanded, setExpanded] = useState(false);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  const toggle = useCallback(() => {
    setExpanded(prev => !prev);
    setPreviewIndex(null);
  }, []);

  const togglePreview = useCallback((i: number) => {
    setPreviewIndex(prev => (prev === i ? null : i));
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
            const isPreviewOpen = previewIndex === i;
            const hasContent = !!cit.text;
            return (
              <div key={`${messageIndex}-cit-${i}`} className="citation-item">
                <span
                  className={`citation-badge${hasContent ? ' has-preview' : ''}`}
                  title={title}
                  onClick={hasContent ? () => togglePreview(i) : undefined}
                >
                  <span className="citation-number">[{i + 1}]</span>
                  <span className="citation-title">{title}</span>
                  {hasContent && (
                    isPreviewOpen
                      ? <ChevronUp size={12} className="citation-chevron-inline" />
                      : <ChevronDown size={12} className="citation-chevron-inline" />
                  )}
                </span>
                {hasContent && isPreviewOpen && (
                  <pre className="citation-preview">{cit.text}</pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
