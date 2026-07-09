import React, { useEffect, useRef } from 'react';
import { ChatMessage } from '../types';
import MessageBubble from './MessageBubble';
import Composer from './Composer';

interface ChatPaneProps {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (message: string) => Promise<void>;
  onShowDetails: (message: ChatMessage) => void;
}

const ChatPane: React.FC<ChatPaneProps> = ({ messages, loading, onSend, onShowDetails }) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const lastAssistantIndex = [...messages].map((m) => m.role).lastIndexOf('assistant');

  return (
    <div className="chat-pane">
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty-state">
            <h2>How can I help you today?</h2>
            <p>
              Ask about course registration, exams, the library, ICT support, hostels, fees,
              the academic calendar, or student conduct.
            </p>
          </div>
        ) : (
          messages.map((message, index) => (
            <MessageBubble
              key={index}
              message={message}
              showFeedback={index === lastAssistantIndex}
              question={message.role === 'assistant' ? messages[index - 1]?.content : undefined}
              onShowDetails={onShowDetails}
            />
          ))
        )}

        {loading && (
          <div className="message-row assistant">
            <div className="message-bubble assistant">
              <div className="typing-indicator">
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <Composer onSend={onSend} loading={loading} />
    </div>
  );
};

export default ChatPane;
