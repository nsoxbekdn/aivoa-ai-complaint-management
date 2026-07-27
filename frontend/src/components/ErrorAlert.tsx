interface ErrorAlertProps {
  title?: string;
  message: string;
  variant?: 'error' | 'warning' | 'success' | 'info';
  onDismiss?: () => void;
}

const ICONS: Record<string, string> = {
  error: '⚠',
  warning: '⚠',
  success: '✓',
  info: 'ℹ',
};

/** One component for every message the user must read: errors, warnings, confirmations. */
export function ErrorAlert({ title, message, variant = 'error', onDismiss }: ErrorAlertProps) {
  return (
    <div className={`alert alert--${variant}`} role={variant === 'error' ? 'alert' : 'status'}>
      <span aria-hidden="true">{ICONS[variant]}</span>
      <div className="alert__content">
        {title && <div className="alert__title">{title}</div>}
        <div>{message}</div>
      </div>
      {onDismiss && (
        <button type="button" className="alert__close" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}
