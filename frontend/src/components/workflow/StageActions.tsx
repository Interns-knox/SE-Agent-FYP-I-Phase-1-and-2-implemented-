import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { approveArtifact, getArtifactErrorMessage } from "../../api/artifacts";
import { getWorkflow } from "../../api/workflow";
import type { Artifact } from "../../types/artifact";
import type { Stage, StageKey } from "../../types/workflow";
import { Button, ErrorMessage } from "../common";
import { computeNextState, STAGE_TYPES } from "./nextState";
import { NEXT_ACTION, STAGE_LABEL, stagePath } from "./stages";
import "./workflow.css";

export interface StageActionsProps {
  projectId: string;
  stageKey: StageKey;
  stage: Stage;
  artifacts: Artifact[];
  onChanged: () => void;
}

/**
 * Bottom-of-page action. It approves what is on screen (never anything automatically), asks
 * the backend to confirm the stage is approved, and only then navigates to the next stage.
 */
export function StageActions({ projectId, stageKey, stage, artifacts, onChanged }: StageActionsProps) {
  const navigate = useNavigate();
  const action = NEXT_ACTION[stageKey];
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  if (!action) {
    return null;
  }
  const state = computeNextState(stage, stageKey, artifacts);

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!state.approved) {
        for (const t of STAGE_TYPES[stageKey] ?? []) {
          const a = artifacts.find((x) => x.type === t);
          if (a && a.status !== "APPROVED") {
            await approveArtifact(a.id); // backend validates and enforces prerequisites
          }
        }
      }
      const wf = await getWorkflow(projectId);
      const fresh = wf.stages.find((s) => s.key === stageKey);
      if (!fresh?.completed) {
        throw new Error("The server did not confirm approval of this stage.");
      }
      onChanged();
      navigate(action.next ? stagePath(projectId, action.next) : `/projects/${projectId}`);
    } catch (e) {
      onChanged(); // the server may have stored a fresh validation result
      setError(e instanceof Error && !("response" in e) ? e.message : getArtifactErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const label = state.approved ? action.doneLabel : action.label;
  return (
    <section className="wf-actions" aria-label="Next stage" data-testid="stage-actions">
      <div className="wf-actions__row">
        <Button
          disabled={!state.enabled || busy}
          onClick={() => void go()}
          data-testid="next-stage-button"
        >
          {busy ? "Working..." : label}
        </Button>
        {action.next ? (
          <span className="artifact__muted">Next: {STAGE_LABEL[action.next]}</span>
        ) : null}
      </div>
      {!state.enabled && state.reason ? (
        <p className="wf-actions__reason" data-testid="next-stage-reason">
          Disabled: {state.reason}
        </p>
      ) : null}
      {state.enabled && !state.approved ? (
        <p className="wf-actions__reason">
          This approves the {stage.name} artifact{(STAGE_TYPES[stageKey] ?? []).length > 1 ? "s" : ""}{" "}
          shown above after the server checks them again. You can reject or edit instead.
        </p>
      ) : null}
      {error ? <ErrorMessage message={error} /> : null}
    </section>
  );
}
