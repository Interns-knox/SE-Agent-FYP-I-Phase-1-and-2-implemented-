import type { ValidationIssue, ValidationResult } from "../../types/artifact";

function IssueList({
  title,
  issues,
  kind,
}: {
  title: string;
  issues: ValidationIssue[];
  kind: "error" | "warning";
}) {
  if (issues.length === 0) {
    return null;
  }
  return (
    <div className={`validation__group validation__group--${kind}`}>
      <h4 className="validation__group-title">
        {title} ({issues.length})
      </h4>
      <ul className="validation__list">
        {issues.map((issue, i) => (
          <li key={`${issue.code}-${i}`} className="validation__item">
            <code className="validation__code">{issue.code}</code>{" "}
            {issue.message}
            {issue.path ? (
              <span className="validation__path"> at {issue.path}</span>
            ) : null}
            {issue.suggestion ? (
              <div className="validation__suggestion">
                Fix: {issue.suggestion}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

const STATUS_LABEL: Record<ValidationResult["status"], string> = {
  PASSED: "Passed",
  PASSED_WITH_WARNINGS: "Passed with warnings",
  FAILED: "Failed",
};

export function ValidationPanel({
  result,
  currentVersion,
}: {
  result: ValidationResult | null;
  currentVersion: number;
}) {
  if (result === null) {
    return <p className="artifact__muted">Not validated yet.</p>;
  }
  const stale =
    result.content_version !== null && result.content_version !== currentVersion;
  return (
    <div className="validation">
      <p className="validation__summary">
        <span
          className={`validation__status validation__status--${result.status.toLowerCase()}`}
        >
          {STATUS_LABEL[result.status]}
        </span>{" "}
        <span className="artifact__muted">
          Deterministic validation, {new Date(result.validated_at).toLocaleString()}
          {stale ? " (for an earlier version)" : ""}
        </span>
      </p>
      <IssueList title="Errors" issues={result.errors} kind="error" />
      <IssueList title="Warnings" issues={result.warnings} kind="warning" />
      {result.errors.length === 0 && result.warnings.length === 0 ? (
        <p className="artifact__muted">No issues found.</p>
      ) : null}
      <details className="validation__checks">
        <summary>Checks run ({result.checks_run.length})</summary>
        <ul>
          {result.checks_run.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
