import { useState } from 'react';

import { useAppDispatch, useAppSelector } from '../app/hooks';
import { askAboutComplaint } from '../features/complaints/complaintsSlice';
import { ErrorAlert } from './ErrorAlert';

interface ComplaintChatProps {
  complaintId: number;
  complaintNumber: string;
}

/** Questions are answered from the stored complaint record only — the backend prompt
 *  refuses to answer anything the record does not contain. */
export function ComplaintChat({ complaintId, complaintNumber }: ComplaintChatProps) {
  const dispatch = useAppDispatch();
  const { messages, pending, error } = useAppSelector((state) => state.complaints.chat);
  const [question, setQuestion] = useState('');

  return (
    <div className="card card--ai">
      <div className="card__header">
        <div>
          <h2>Ask about {complaintNumber}</h2>
          <p>Answers use only this complaint record.</p>
        </div>
        <span className="badge badge--ai">AI · review required</span>
      </div>

      <div className="card__body">
        {error && <ErrorAlert title="The assistant could not answer" message={error} />}

        {messages.length === 0 ? (
          <p className="text-small text-muted">
            Try “What is the batch number?” or “Why was this rated high risk?”.
          </p>
        ) : (
          <div className="chat__messages">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`chat__message chat__message--${message.role}`}
              >
                {message.text}
              </div>
            ))}
          </div>
        )}

        {pending && <div className="text-small text-muted">Thinking…</div>}

        <form
          className="chat__form"
          onSubmit={(event) => {
            event.preventDefault();
            const trimmed = question.trim();
            if (!trimmed || pending) return;
            dispatch(askAboutComplaint({ id: complaintId, question: trimmed }));
            setQuestion('');
          }}
        >
          <input
            type="text"
            value={question}
            disabled={pending}
            placeholder="Ask a question about this complaint…"
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button type="submit" className="button button--primary" disabled={pending || !question.trim()}>
            Ask
          </button>
        </form>
      </div>
    </div>
  );
}
