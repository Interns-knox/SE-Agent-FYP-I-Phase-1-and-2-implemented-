import "./common.css";

const TONE: Record<string, string> = {
  APPROVED: "ok",
  REJECTED: "bad",
  PENDING_REVIEW: "warn",
  REQUIRES_REVIEW: "warn",
  IN_PROGRESS: "info",
  NOT_STARTED: "muted",
  BLOCKED: "muted",
};

/** Colored status label. Shows the raw status so nothing is hidden behind a friendly word. */
export function Pill({ value }: { value: string }) {
  return (
    <span className={`pill pill--${TONE[value] ?? "muted"}`}>
      {value.replace(/_/g, " ")}
    </span>
  );
}
