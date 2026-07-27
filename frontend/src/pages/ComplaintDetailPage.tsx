import { useParams } from 'react-router-dom';

import { ComplaintDetail } from '../components/ComplaintDetail';
import { ErrorAlert } from '../components/ErrorAlert';

export function ComplaintDetailPage() {
  const { complaintId } = useParams<{ complaintId: string }>();
  const parsed = Number(complaintId);

  if (!complaintId || Number.isNaN(parsed)) {
    return (
      <div className="page">
        <ErrorAlert title="Invalid complaint" message={`"${complaintId}" is not a complaint id.`} />
      </div>
    );
  }

  return (
    <div className="page">
      <ComplaintDetail complaintId={parsed} />
    </div>
  );
}
