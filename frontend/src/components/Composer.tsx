import React, { useRef, useState } from 'react';
import { FaArrowUp } from 'react-icons/fa';

interface ComposerProps {
  onSend: (message: string) => Promise<void>;
  loading: boolean;
}

const Composer: React.FC<ComposerProps> = ({ onSend, loading }) => {
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  };

  const submit = async () => {
    const trimmed = text.trim();
    if (!trimmed) {
      setError('Type a message first.');
      return;
    }
    setError(null);
    setText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    try {
      await onSend(trimmed);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!loading) submit();
    }
  };

  return (
    <div className="composer">
      {error && <div className="composer-error">{error}</div>}
      <div className="composer-inner">
        <textarea
          ref={textareaRef}
          rows={1}
          placeholder="Message the assistant..."
          value={text}
          disabled={loading}
          onChange={(e) => {
            setText(e.target.value);
            resize();
          }}
          onKeyDown={handleKeyDown}
        />
        <div className="composer-controls">
          <button className="send-btn" onClick={submit} disabled={loading} aria-label="Send">
            <FaArrowUp size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default Composer;
