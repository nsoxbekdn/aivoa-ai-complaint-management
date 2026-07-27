import { useEffect, useRef, useState } from 'react';

import { useAppDispatch, useAppSelector } from '../app/hooks';
import {
  analyzeComplaint,
  clearIntake,
  continueIntakeChat,
  dismissAnalysisError,
  setPastedText,
  setUploadedFile,
} from '../features/complaints/complaintsSlice';
import {
  hasReporterFacts,
  isReporterReadyToLodge,
} from '../features/complaints/formUtils';
import { ErrorAlert } from './ErrorAlert';

const MAX_UPLOAD_MB = 5;
const ACCEPTED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg'];
const COMPLETENESS_LABEL_BY_FIELD: Record<string, string> = {
  complaint_source: 'complaint source',
  customer_name: 'customer name',
  customer_contact: 'customer contact',
  product_name: 'product name',
  product_strength_grade: 'product strength / grade',
  batch_lot_number: 'batch / lot number',
  manufacturing_date: 'manufacturing date',
  expiry_date: 'expiry date',
  quantity_affected: 'quantity affected',
  quantity_unit: 'quantity unit',
  complaint_type: 'complaint type',
  complaint_date: 'complaint date',
  complaint_details: 'complaint details',
};

function PaperclipIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M8.5 12.5 14.9 6a3 3 0 1 1 4.2 4.2l-8.5 8.5a5 5 0 0 1-7.1-7.1l8.1-8.1"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m4 4 17 8-17 8 3-8-3-8Zm3 8h14" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

/** Reporter-facing chat. Internal risk, investigation and CAPA remain on the lodged record. */
export function ComplaintIntakePanel() {
  const dispatch = useAppDispatch();
  const { analysis, analyzing, analysisError, formData, intakeChat } = useAppSelector(
    (state) => state.complaints,
  );

  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const pending = analyzing || intakeChat.pending;
  const canSend = Boolean(message.trim() || file) && !pending;
  const completeness = analysis?.completeness;
  const formHasReporterFacts = hasReporterFacts(formData);
  const reporterReadyToLodge = isReporterReadyToLodge(formData);
  const unavailableLabels = new Set(
    intakeChat.dialogueState.unavailable_fields.map(
      (field) => COMPLETENESS_LABEL_BY_FIELD[field] ?? field.replaceAll('_', ' '),
    ),
  );
  const missing = completeness
    ? [
        ...completeness.missing_critical_fields,
        ...completeness.missing_optional_fields.filter(
          (field) => field !== 'initial severity' && field !== 'priority',
        ),
      ].filter((field) => !unavailableLabels.has(field))
    : [];

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' });
  }, [intakeChat.messages, pending]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 132)}px`;
  }, [message]);

  const chooseFile = (candidate: File | undefined) => {
    if (!candidate) return;
    const lower = candidate.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension))) {
      setLocalError('Attach a PDF, PNG, JPG, or JPEG complaint document.');
      return;
    }
    if (candidate.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setLocalError(`"${candidate.name}" is larger than the ${MAX_UPLOAD_MB} MB limit.`);
      return;
    }
    setLocalError(null);
    setFile(candidate);
    dispatch(setUploadedFile({ name: candidate.name, size: candidate.size }));
  };

  const removeFile = () => {
    setFile(null);
    dispatch(setUploadedFile(null));
  };

  const handleSend = () => {
    if (!canSend) return;
    const text = message.trim();
    setLocalError(null);
    if (!analysis && !formHasReporterFacts) {
      dispatch(setPastedText(text));
      dispatch(analyzeComplaint({ text: text || undefined, file: file ?? undefined }));
    } else {
      dispatch(
        continueIntakeChat({
          message: text,
          currentFields: formData,
          history: intakeChat.messages,
          dialogueState: intakeChat.dialogueState,
          file: file ?? undefined,
        }),
      );
    }
    setMessage('');
    removeFile();
  };

  const handleNewComplaint = () => {
    setFile(null);
    setMessage('');
    setLocalError(null);
    dispatch(clearIntake());
  };

  return (
    <div className="card card--ai intake-chat">
      <div className="card__header intake-chat__header">
        <div className="intake-chat__identity">
          <span className="intake-chat__avatar" aria-hidden="true">AI</span>
          <div>
            <h2>Complaint assistant</h2>
            <p>Explain it naturally. I will gather the facts with you.</p>
          </div>
        </div>
        <span className="intake-chat__online">Online</span>
      </div>

      <div className="card__body intake-chat__body">
        {(analysisError || localError || intakeChat.error) && (
          <ErrorAlert
            title="The assistant could not continue"
            message={analysisError ?? localError ?? intakeChat.error ?? ''}
            onDismiss={() => {
              setLocalError(null);
              dispatch(dismissAnalysisError());
            }}
          />
        )}

        <div className="intake-chat__messages" ref={messagesRef} aria-live="polite">
          {intakeChat.messages.map((chatMessage, index) => (
            <div
              key={`${chatMessage.role}-${index}`}
              className={`intake-chat__message-row intake-chat__message-row--${chatMessage.role}`}
            >
              {chatMessage.role === 'assistant' && (
                <span className="intake-chat__mini-avatar" aria-hidden="true">AI</span>
              )}
              <div className={`intake-chat__message intake-chat__message--${chatMessage.role}`}>
                {chatMessage.attachmentName && (
                  <span className="intake-chat__bubble-attachment">
                    <PaperclipIcon />
                    {chatMessage.attachmentName}
                  </span>
                )}
                {chatMessage.text && <span>{chatMessage.text}</span>}
                {chatMessage.ocrUsed && (
                  <span className="intake-chat__ocr-note">OCR used · please verify extracted details</span>
                )}
              </div>
            </div>
          ))}

          {pending && (
            <div className="intake-chat__message-row intake-chat__message-row--assistant">
              <span className="intake-chat__mini-avatar" aria-hidden="true">AI</span>
              <div className="intake-chat__message intake-chat__message--assistant intake-chat__typing">
                <span />
                <span />
                <span />
                <span className="sr-only">
                  {analyzing ? 'Reading the complaint' : 'Checking the information'}
                </span>
              </div>
            </div>
          )}
        </div>

        {analysis?.warnings.some((warning) => /ocr|vision|attachment/i.test(warning)) && (
          <div className="alert alert--warning intake-chat__document-warning">
            {analysis.warnings.find((warning) => /ocr|vision|attachment/i.test(warning))}
          </div>
        )}

        {completeness && (
          <div className="intake-chat__status">
            <div className="row-between">
              <span>{reporterReadyToLodge ? 'Ready to lodge' : 'Building the complaint'}</span>
              <strong>{completeness.score}%</strong>
            </div>
            <div className="meter">
              <div
                className={`meter__fill meter__fill--${reporterReadyToLodge ? 'ok' : 'warn'}`}
                style={{ width: `${completeness.score}%` }}
              />
            </div>
            {missing.length > 0 && (
              <div className="text-small text-muted">
                Still useful: {missing.slice(0, 3).join(', ')}
                {missing.length > 3 ? ` and ${missing.length - 3} more` : ''}
              </div>
            )}
          </div>
        )}

        <div className="intake-chat__composer-shell">
          {file && (
            <div className="intake-chat__attachment">
              <span className="intake-chat__attachment-icon"><PaperclipIcon /></span>
              <span>
                <strong>{file.name}</strong>
                <small>{file.type || 'Complaint attachment'}</small>
              </span>
              <button type="button" aria-label={`Remove ${file.name}`} onClick={removeFile}>×</button>
            </div>
          )}

          <div className="intake-chat__composer">
            <button
              type="button"
              className="intake-chat__attach-button"
              aria-label="Attach PDF or image"
              title="Attach PDF, PNG, or JPG"
              disabled={pending}
              onClick={() => inputRef.current?.click()}
            >
              <PaperclipIcon />
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              hidden
              onChange={(event) => {
                chooseFile(event.target.files?.[0]);
                event.target.value = '';
              }}
            />
            <textarea
              ref={textareaRef}
              rows={1}
              value={message}
              disabled={pending}
              aria-label="Message the complaint assistant"
              placeholder={
                analysis || formHasReporterFacts
                  ? 'Ask a question, add or correct a detail…'
                  : 'Describe what happened…'
              }
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  handleSend();
                }
              }}
            />
            <button
              type="button"
              className="intake-chat__send-button"
              aria-label="Send message"
              disabled={!canSend}
              onClick={handleSend}
            >
              {pending ? <span className="spinner" aria-hidden="true" /> : <SendIcon />}
            </button>
          </div>
          <div className="intake-chat__composer-hint">
            <span>PDF, PNG or JPG · scanned files supported</span>
            <span>Enter to send · Shift+Enter for a new line</span>
          </div>
        </div>

        {reporterReadyToLodge && (
          <div className="alert alert--success intake-chat__ready">
            Important details are present. Review the form, then lodge the complaint.
          </div>
        )}

        {(analysis || formHasReporterFacts) && (
          <button type="button" className="button button--link intake-chat__new" onClick={handleNewComplaint}>
            Start a new complaint
          </button>
        )}
      </div>
    </div>
  );
}
