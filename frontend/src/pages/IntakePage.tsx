import { ComplaintForm } from '../components/ComplaintForm';
import { ComplaintIntakePanel } from '../components/ComplaintIntakePanel';

export function IntakePage() {
  return (
    <div className="page">
      <div className="page__heading">
        <h1>New customer complaint</h1>
        <p>
          Describe what happened in your own words. The assistant will ask for missing details
          and help complete the form.
        </p>
      </div>

      <div className="intake-layout">
        <ComplaintForm />
        <ComplaintIntakePanel />
      </div>
    </div>
  );
}
