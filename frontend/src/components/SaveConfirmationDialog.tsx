import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAppDispatch, useAppSelector } from '../app/hooks';
import { clearIntake } from '../features/complaints/complaintsSlice';

/** Confirmation the user cannot miss.
 *  The Save button sits at the bottom of a long form, so an inline banner at the
 *  top of that form scrolls out of view exactly when it matters. A native
 *  <dialog> takes focus, dims the page and offers the two next steps. */
export function SaveConfirmationDialog() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const savedComplaint = useAppSelector((state) => state.complaints.savedComplaint);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);

  // Open once per save. The ref starts at whatever is already saved so that coming
  // back to the intake page does not re-open the dialog for a record already seen.
  const shownIdRef = useRef<number | null>(savedComplaint?.id ?? null);
  useEffect(() => {
    const id = savedComplaint?.id ?? null;
    if (id !== null && id !== shownIdRef.current) {
      shownIdRef.current = id;
      setOpen(true);
    }
  }, [savedComplaint?.id]);

  // showModal() is the only way to get the ::backdrop and the focus trap.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  if (!savedComplaint) return null;

  const startAnother = () => {
    setOpen(false);
    dispatch(clearIntake());
  };

  const openRecord = () => {
    setOpen(false);
    navigate(`/complaints/${savedComplaint.id}`);
  };

  return (
    <dialog
      ref={dialogRef}
      className="save-dialog"
      aria-labelledby="save-dialog-title"
      onClose={() => setOpen(false)}
      onCancel={() => setOpen(false)}
    >
      <div className="save-dialog__icon" aria-hidden="true">
        ✓
      </div>
      <h2 id="save-dialog-title">Complaint lodged</h2>
      <p className="save-dialog__number">{savedComplaint.complaint_number}</p>

      <dl className="save-dialog__summary">
        <div>
          <dt>Product</dt>
          <dd>{savedComplaint.product_name}</dd>
        </div>
        {savedComplaint.batch_lot_number && (
          <div>
            <dt>Batch</dt>
            <dd>{savedComplaint.batch_lot_number}</dd>
          </div>
        )}
      </dl>

      <p className="save-dialog__note">
        The complaint is now available in the internal QA workspace for investigation.
      </p>

      <div className="save-dialog__actions">
        <button type="button" className="button button--ghost" onClick={startAnother}>
          Lodge another complaint
        </button>
        <button type="button" className="button button--primary" onClick={openRecord}>
          Open QA workspace
        </button>
      </div>

      <button
        type="button"
        className="save-dialog__close"
        onClick={() => setOpen(false)}
        aria-label="Close"
      >
        ×
      </button>
    </dialog>
  );
}
