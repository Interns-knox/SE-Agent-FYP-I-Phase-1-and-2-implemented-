import { useCallback, useEffect, useState } from "react";
import {
  getArtifactErrorMessage,
  getConsistency,
  getDependencies,
} from "../../api/artifacts";
import type { Consistency, TraceLink } from "../../types/artifact";
import { Button, Card, ErrorMessage, LoadingSpinner } from "../common";
import { ValidationPanel } from "./ValidationPanel";
import "./artifacts.css";

/** Dependency model view: links between features, requirements, components, domain entities and UML diagrams. */
export function TraceabilityPanel({
  projectId,
  refreshKey,
}: {
  projectId: string;
  refreshKey: number;
}) {
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [consistency, setConsistency] = useState<Consistency | null>(null);
  const [checking, setChecking] = useState<boolean>(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const run = async () => {
      setLoading(true);
      try {
        const result = await getDependencies(projectId);
        if (active) {
          setLinks(result);
          setError(null);
        }
      } catch (e) {
        if (active) {
          setError(getArtifactErrorMessage(e));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void run();
    return () => {
      active = false;
    };
  }, [projectId, refreshKey]);

  const check = useCallback(async () => {
    setChecking(true);
    setCheckError(null);
    try {
      setConsistency(await getConsistency(projectId));
    } catch (e) {
      setCheckError(getArtifactErrorMessage(e));
    } finally {
      setChecking(false);
    }
  }, [projectId]);

  return (
    <Card className="artifact">
      <header className="artifact__header">
        <h3 className="artifact__title">Dependency model</h3>
      </header>
      <p className="artifact__muted">
        Links are derived from artifact content: requirement → feature,
        component → requirement, domain entity → requirement, UML diagram →
        domain entity/component/requirement. Arrows read "depends on".
      </p>
      <div className="artifact__actions">
        <Button variant="secondary" disabled={checking} onClick={() => void check()}>
          Check cross-artifact consistency
        </Button>
      </div>
      {checking ? <LoadingSpinner label="Checking..." /> : null}
      {checkError ? <ErrorMessage message={checkError} /> : null}
      {consistency ? (
        <ValidationPanel result={consistency.validation} currentVersion={0} />
      ) : null}
      {loading ? <LoadingSpinner label="Loading links..." /> : null}
      {error ? <ErrorMessage message={error} /> : null}
      {!loading && !error && links.length === 0 ? (
        <p className="artifact__muted">
          No links yet. Generate and approve requirements first.
        </p>
      ) : null}
      {links.length > 0 ? (
        <div className="table-wrap">
          <table className="artifact-table">
            <thead>
              <tr>
                <th>From</th>
                <th>Relation</th>
                <th>To</th>
                <th>Declared in</th>
              </tr>
            </thead>
            <tbody>
              {links.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.source_kind} <code>{l.source_ref.slice(0, 36)}</code>
                  </td>
                  <td>{l.relation}</td>
                  <td>
                    {l.target_kind} <code>{l.target_ref.slice(0, 36)}</code>
                  </td>
                  <td>
                    {l.owner_type} ({l.owner_status})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}
