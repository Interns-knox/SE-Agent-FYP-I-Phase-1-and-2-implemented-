import "./common.css";

export interface LoadingSpinnerProps {
  label?: string;
}

export function LoadingSpinner({ label = "Loading..." }: LoadingSpinnerProps) {
  return (
    <div className="spinner-wrap" role="status">
      <span className="spinner" aria-hidden="true" />
      <span className="spinner-label" aria-hidden="true">
        {label}
      </span>
      <span className="visually-hidden">{label}</span>
    </div>
  );
}
