import { useNavigate } from "react-router-dom";
import type { Stage } from "../../types/workflow";
import { Button } from "../common";
import { BLOCK_TITLE, STAGE_LABEL, stagePath } from "./stages";
import "./workflow.css";

/** Shown instead of a generic error when a stage's prerequisite stage is not approved. */
export function BlockedStage({ stage, projectId }: { stage: Stage; projectId: string }) {
  const navigate = useNavigate();
  const required = stage.required_stage;
  if (required === null) {
    return null;
  }
  return (
    <section className="wf-blocked" role="alert" aria-label={BLOCK_TITLE[required]}>
      <h2 className="wf-blocked__title">{BLOCK_TITLE[required]}</h2>
      <p>{stage.blocked_reason}</p>
      {stage.suggested_action ? (
        <p className="artifact__muted">What to do: {stage.suggested_action}</p>
      ) : null}
      <Button onClick={() => navigate(stagePath(projectId, required))}>
        Back to {STAGE_LABEL[required]}
      </Button>
    </section>
  );
}
