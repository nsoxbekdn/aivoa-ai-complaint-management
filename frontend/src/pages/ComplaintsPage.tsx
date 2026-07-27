import { ComplaintList } from '../components/ComplaintList';

export function ComplaintsPage() {
  return (
    <div className="page">
      <div className="page__heading">
        <h1>Saved complaints</h1>
        <p>Every complaint a reviewer has approved and written to the database.</p>
      </div>
      <ComplaintList />
    </div>
  );
}
