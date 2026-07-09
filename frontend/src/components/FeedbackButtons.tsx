import React, { useState } from 'react';
import { FaThumbsUp, FaMeh, FaThumbsDown } from 'react-icons/fa';
import { sendFeedback } from '../services/api';

interface FeedbackButtonsProps {
  question: string;
  answer: string;
}

const FeedbackButtons: React.FC<FeedbackButtonsProps> = ({ question, answer }) => {
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const handleFeedback = async (rating: string) => {
    const success = await sendFeedback(question, answer, rating);
    setToast(success ? 'Thanks for the feedback!' : 'Could not save feedback.');
    if (success) setSelected(rating);
    setTimeout(() => setToast(null), 3000);
  };

  return (
    <div className="feedback-row">
      <span>Was this helpful?</span>
      <button
        className={`feedback-btn ${selected === 'Good' ? 'active' : ''}`}
        onClick={() => handleFeedback('Good')}
      >
        <FaThumbsUp size={12} /> Good
      </button>
      <button
        className={`feedback-btn ${selected === 'Average' ? 'active' : ''}`}
        onClick={() => handleFeedback('Average')}
      >
        <FaMeh size={12} /> Average
      </button>
      <button
        className={`feedback-btn ${selected === 'Poor' ? 'active' : ''}`}
        onClick={() => handleFeedback('Poor')}
      >
        <FaThumbsDown size={12} /> Poor
      </button>
      {toast && <div className="feedback-toast">{toast}</div>}
    </div>
  );
};

export default FeedbackButtons;
