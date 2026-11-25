import { Link } from "react-router-dom";
import type { Stage, Workflow } from "../../types/workflow";
import { Pill } from "../common";
import { stagePath } from "./stages";
import "./workflow.css";

function StepBody({ stage, current }: { stage: Stage; current: boolean }) {
  const icon = stage.completed ? "✓" : stage.blocked ? "🔒" : String(stage.number);
  return (
    <>
      <span className="wf-step__num" aria-hidden="true">
        {icon}
      </span>
      <span className="wf-step__text">
        <span className="wf-step__name">{stage.name}</span>
        <Pill value={stage.status} />
        {current ? <span className="wf-step__current">current</span> : null}
      </span>
    </>
  );
}

export interface WorkflowProgressProps {
  projectId: string;
  workflow: Workflow | null;
  loading?: boolean;
}

/**
 * The six SDLC stages with status, approval and lock state. Locked stages are not links;
 * the backend still enforces every gate if someone opens a locked URL directly.
 */
export function WorkflowProgress({
  projectId,
  workflow,
  loading = false,
}: WorkflowProgressProps) {
  if (workflow === null) {
    return (
      <nav className="wf" aria-label="Workflow progress">
        <p className="artifact__muted">{loading ? "Loading workflow..." : "Workflow unavailable."}</p>
      </nav>
    );
  }
  return (
    <nav className="wf" aria-label="Workflow progress">
      <ol className="wf__list">
        {workflow.stages.map((stage) => {
          const current = stage.key === workflow.current_stage;
          const cls = [
            "wf-step",
            stage.completed ? "wf-step--done" : "",
            stage.blocked ? "wf-step--locked" : "",
            stage.status === "REQUIRES_REVIEW" ? "wf-step--review" : "",
            current ? "wf-step--current" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <li key={stage.key} className={cls} data-stage={stage.key} data-status={stage.status}>
              {stage.blocked ? (
                <span
                  className="wf-step__link"
                  aria-disabled="true"
                  title={stage.blocked_reason ?? "Locked"}
                >
                  <StepBody stage={stage} current={current} />
                </span>
              ) : (
                <Link
                  className="wf-step__link"
                  to={stagePath(projectId, stage.key)}
                  aria-current={current ? "step" : undefined}
                >
                  <StepBody stage={stage} current={current} />
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
