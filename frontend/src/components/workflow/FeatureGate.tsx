import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getArtifactErrorMessage } from "../../api/artifacts";
import { getWorkflow } from "../../api/workflow";
import type { Stage } from "../../types/workflow";
import { Button, ErrorMessage } from "../common";
import { stagePath } from "./stages";
import "./workflow.css";

export interface FeatureGateProps {
  projectId: string;
  stage: Stage | null;
  onRefresh: () => void;
}

/** Feature review summary and the "Move to Requirements" action. */
export function FeatureGate({ projectId, stage, onRefresh }: FeatureGateProps) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  if (stage === null || !stage.counts) {
    return null;
  }
  const c = stage.counts;
  const ready = stage.completed;
  const reason = ready ? null : (stage.gate_reason ?? "Review the extracted features first.");

  const proceed = async () => {
    setBusy(true);
    setError(null);
    try {
      const wf = await getWorkflow(projectId); // never trust the page's cached state
      const fresh = wf.stages.find((s) => s.key === "FEATURES");
      if (fresh?.completed) {
        navigate(stagePath(projectId, "REQUIREMENTS"));
      } else {
        setError(fresh?.gate_reason ?? "Features are not ready for requirements yet.");
        onRefresh();
      }
    } catch (e) {
      setError(getArtifactErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="wf-gate" aria-label="Feature review summary" data-testid="feature-gate">
      <dl className="wf-counts">
        <div>
          <dt>Extracted features</dt>
          <dd data-testid="count-total">{c.total}</dd>
        </div>
        <div>
          <dt>Approved</dt>
          <dd data-testid="count-approved">{c.approved}</dd>
        </div>
        <div>
          <dt>Pending review</dt>
          <dd data-testid="count-pending">{c.pending}</dd>
        </div>
        <div>
          <dt>Rejected</dt>
          <dd data-testid="count-rejected">{c.rejected}</dd>
        </div>
      </dl>
      <div className="wf-actions__row">
        <Button disabled={!ready || busy} onClick={() => void proceed()} data-testid="move-to-requirements">
          Move to Requirements
        </Button>
        <span className="artifact__muted">Only approved features are used to generate requirements.</span>
      </div>
      {reason ? (
        <p className="wf-actions__reason" data-testid="feature-gate-reason">
          Disabled: {reason}
        </p>
      ) : null}
      {error ? <ErrorMessage message={error} /> : null}
    </section>
  );
}
