interface LoadingIndicatorProps {
  label?: string;
}

export function LoadingIndicator({ label = 'Loading…' }: LoadingIndicatorProps) {
  return (
    <div className="loading-inline" role="status">
      <span className="spinner spinner--dark" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
