import React from 'react';
import ReactMarkdown from 'react-markdown';
import { ChatMessage } from '../types';
import FeedbackButtons from './FeedbackButtons';

interface MessageBubbleProps {
  message: ChatMessage;
  showFeedback: boolean;
  question?: string;
  onShowDetails: (message: ChatMessage) => void;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  showFeedback,
  question,
  onShowDetails,
}) => {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="message-row user">
        <div className="message-bubble user">{message.content}</div>
      </div>
    );
  }

  const sourceCount = message.sources?.length ?? 0;

  return (
    <div className={`message-row assistant ${message.isError ? 'assistant-error' : ''}`}>
      <div className="message-bubble assistant">
        <ReactMarkdown>{message.content}</ReactMarkdown>

        {!message.isError && message.usedKb && (
          <div className="message-meta">
            <button
              className="kb-chip"
              onClick={() => onShowDetails(message)}
              title={`Used ${sourceCount} source${sourceCount === 1 ? '' : 's'} — click for details`}
            >
              📚 Used knowledge base
            </button>
          </div>
        )}

        {showFeedback && !message.isError && (
          <FeedbackButtons question={question ?? ''} answer={message.content} />
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
