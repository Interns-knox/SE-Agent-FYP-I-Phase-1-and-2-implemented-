import { useCallback, useState } from "react";
import { Button, ErrorMessage, LoadingSpinner } from "../common";
import { getContext } from "../../api/context";
import { getErrorMessage } from "../../api/client";
import type { ContextResponse } from "../../types/context";
import "./workspace.css";

export interface ContextPanelProps {
  projectId: string;
}

function formatTimestamp(iso: string | null): string {
  if (iso === null) {
    return "Never";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function ContextPanel({ projectId }: ContextPanelProps) {
  const [expanded, setExpanded] = useState<boolean>(false);
  const [context, setContext] = useState<ContextResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadContext = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getContext(projectId);
      setContext(result);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const toggle = useCallback(() => {
    const next = !expanded;
    setExpanded(next);
    if (next && context === null && !loading) {
      void loadContext();
    }
  }, [expanded, context, loading, loadContext]);

  return (
    <div className="context-panel">
      <Button
        variant="secondary"
        onClick={toggle}
        aria-expanded={expanded}
      >
        {expanded ? "Hide context" : "Inspect context"}
      </Button>

      {expanded ? (
        <div className="context-panel__body">
          {loading ? <LoadingSpinner label="Loading context..." /> : null}
          {error ? (
            <ErrorMessage message={error} onRetry={loadContext} />
          ) : null}

          {!loading && !error && context ? (
            <>
              <div className="context-panel__actions">
                <Button
                  variant="secondary"
                  disabled={loading}
                  onClick={() => {
                    void loadContext();
                  }}
                >
                  Refresh
                </Button>
              </div>

              <dl className="context-panel__facts">
                <div className="context-panel__fact">
                  <dt>Current stage</dt>
                  <dd>{context.project.stage}</dd>
                </div>
                <div className="context-panel__fact">
                  <dt>Last extraction</dt>
                  <dd>{formatTimestamp(context.last_extraction_at)}</dd>
                </div>
                <div className="context-panel__fact">
                  <dt>Approved features</dt>
                  <dd>{context.approved_features.length}</dd>
                </div>
              </dl>

              <div className="context-panel__approved">
                <h4 className="context-panel__subtitle">Approved features</h4>
                {context.approved_features.length === 0 ? (
                  <p className="context-panel__empty">
                    No approved features yet.
                  </p>
                ) : (
                  <ul className="context-panel__list">
                    {context.approved_features.map((feature) => (
                      <li key={feature.id} className="context-panel__item">
                        <span className="context-panel__item-name">
                          {feature.name}
                        </span>
                        <span className="context-panel__item-version">
                          v{feature.current_version}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
