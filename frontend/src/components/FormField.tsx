import type { ChangeEvent, ReactNode } from 'react';

interface Option {
  value: string;
  label: string;
}

interface FormFieldProps {
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: 'text' | 'date' | 'number' | 'email' | 'select' | 'textarea';
  options?: Option[];
  required?: boolean;
  disabled?: boolean;
  error?: string;
  hint?: string;
  placeholder?: string;
  /** True when the value was written by the AI and has not been edited yet. */
  aiFilled?: boolean;
  fullWidth?: boolean;
  rows?: number;
  children?: ReactNode;
}

export function FormField({
  name,
  label,
  value,
  onChange,
  type = 'text',
  options = [],
  required = false,
  disabled = false,
  error,
  hint,
  placeholder,
  aiFilled = false,
  fullWidth = false,
  rows = 5,
}: FormFieldProps) {
  const classNames = [
    'field',
    fullWidth ? 'field--full' : '',
    aiFilled ? 'field--ai' : '',
    error ? 'field--invalid' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const handleChange = (
    event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => onChange(event.target.value);

  const shared = {
    id: name,
    name,
    value,
    disabled,
    placeholder,
    'aria-invalid': Boolean(error),
    'aria-describedby': error ? `${name}-error` : undefined,
    onChange: handleChange,
  };

  return (
    <div className={classNames}>
      <label htmlFor={name}>
        {label}
        {required && (
          <span className="required" aria-hidden="true">
            *
          </span>
        )}
        {aiFilled && <span className="field__ai-tag">AI</span>}
      </label>

      {type === 'select' ? (
        <select {...shared}>
          <option value="">— Select —</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : type === 'textarea' ? (
        <textarea {...shared} rows={rows} />
      ) : (
        <input {...shared} type={type} />
      )}

      {hint && !error && <div className="field__hint">{hint}</div>}
      {error && (
        <span className="field__error" id={`${name}-error`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
