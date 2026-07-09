import React, { useEffect } from 'react';
import { FaTimes } from 'react-icons/fa';
import { ChatMessage } from '../types';

interface SourcesPanelProps {
  message: ChatMessage | null;
  onClose: () => void;
}

const SourcesPanel: React.FC<SourcesPanelProps> = ({ message, onClose }) => {
  useEffect(() => {
    if (!message) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [message, onClose]);

  if (!message) return null;

  const sources = message.sources ?? [];

  return (
    <>
      <div className="sources-backdrop" onClick={onClose} />
      <aside className="sources-panel">
        <div className="sources-panel-header">
          <h3>Answer details</h3>
          <button className="sources-panel-close" onClick={onClose} aria-label="Close">
            <FaTimes size={14} />
          </button>
        </div>

        <div className="sources-panel-body">
          <div className="sources-panel-row">
            <span className="sources-panel-label">Model</span>
            <span>{message.model ?? '—'}</span>
          </div>
          <div className="sources-panel-row">
            <span className="sources-panel-label">Response time</span>
            <span>{typeof message.generationTime === 'number' ? `${message.generationTime}s` : '—'}</span>
          </div>
          <div className="sources-panel-row">
            <span className="sources-panel-label">Tokens used</span>
            <span>{message.tokensUsed ?? '—'}</span>
          </div>

          <div className="sources-panel-label sources-panel-section-title">
            Sources ({sources.length})
          </div>
          <div className="sources-panel-list">
            {sources.length === 0 ? (
              <div className="sources-panel-item">No sources were used for this answer.</div>
            ) : (
              sources.map((source, i) => (
                <div className="sources-panel-item" key={i}>
                  <div className="sources-panel-item-meta">
                    <span>{source.heading ? `${source.source} - ${source.heading}` : source.source}</span>
                    <span>{source.score.toFixed(2)}</span>
                  </div>
                  <div className="sources-panel-item-text">{source.text}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </aside>
    </>
  );
};

export default SourcesPanel;
