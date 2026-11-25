import { useCallback, useEffect, useState } from "react";
import {
  approveArtifact,
  critiqueArtifact,
  editArtifact,
  generateArtifact,
  getArtifactDecisions,
  getArtifactDiff,
  getArtifactErrorMessage,
  getArtifactVersions,
  getEmbeddedValidation,
  regenerateArtifact,
  rejectArtifact,
  validateArtifact,
} from "../../api/artifacts";
import type { ArtifactDiff } from "../../api/artifacts";
import type {
  Artifact,
  ArtifactDecision,
  ArtifactType,
  ArtifactVersion,
  ValidationResult,
} from "../../types/artifact";
import { Badge, Button, Card, ErrorMessage, LoadingSpinner } from "../common";
import { renderContent } from "./renderContent";
import { ValidationPanel } from "./ValidationPanel";
import "./artifacts.css";

export interface ArtifactPanelProps {
  projectId: string;
  type: ArtifactType;
  heading: string;
  /** What must exist (and be approved) before generation is possible. */
  prerequisite: string;
  artifact: Artifact | undefined;
  onChanged: () => void;
  /** Stage is locked (an earlier stage is not approved): generating, editing and approving are off. */
  locked?: boolean;
  lockedReason?: string | null;
}

type Action =
  | "generate"
  | "regenerate"
  | "validate"
  | "approve"
  | "reject"
  | "save"
  | "critique";

const ACTION_LABEL: Record<Action, string> = {
  generate: "Generating with the local AI model. This can take a few minutes...",
  regenerate: "Regenerating with the local AI model. This can take a few minutes...",
  validate: "Validating...",
  approve: "Approving...",
  reject: "Rejecting...",
  save: "Saving...",
  critique: "Requesting AI critique...",
};

function fmt(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function ArtifactPanel({
  projectId,
  type,
  heading,
  prerequisite,
  artifact,
  onChanged,
  locked = false,
  lockedReason = null,
}: ArtifactPanelProps) {
  const [busy, setBusy] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [blockingValidation, setBlockingValidation] =
    useState<ValidationResult | null>(null);
  const [feedback, setFeedback] = useState<string>("");
  const [editing, setEditing] = useState<boolean>(false);
  const [draft, setDraft] = useState<string>("");
  const [changeNote, setChangeNote] = useState<string>("");
  const [showVersions, setShowVersions] = useState<boolean>(false);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [decisions, setDecisions] = useState<ArtifactDecision[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [viewVersion, setViewVersion] = useState<ArtifactVersion | null>(null);
  const [diffView, setDiffView] = useState<ArtifactDiff | null>(null);

  const artifactId = artifact?.id;
  const artifactVersion = artifact?.current_version;

  useEffect(() => {
    if (!showVersions || artifactId === undefined) {
      return;
    }
    let active = true;
    const run = async () => {
      setHistoryLoading(true);
      setHistoryError(null);
      try {
        const [v, d] = await Promise.all([
          getArtifactVersions(artifactId),
          getArtifactDecisions(artifactId),
        ]);
        if (active) {
          setVersions(v);
          setDecisions(d);
        }
      } catch (e) {
        if (active) {
          setHistoryError(getArtifactErrorMessage(e));
        }
      } finally {
        if (active) {
          setHistoryLoading(false);
        }
      }
    };
    void run();
    return () => {
      active = false;
    };
    // artifactVersion changes whenever a new version is persisted.
  }, [showVersions, artifactId, artifactVersion]);

  const run = useCallback(
    async (action: Action, fn: () => Promise<unknown>, done: string) => {
      setBusy(action);
      setError(null);
      setSuccess(null);
      setBlockingValidation(null);
      try {
        await fn();
        setSuccess(done);
        onChanged();
        return true;
      } catch (e) {
        setError(getArtifactErrorMessage(e));
        setBlockingValidation(getEmbeddedValidation(e));
        if (action === "approve") {
          onChanged(); // the server stores the fresh validation result
        }
        return false;
      } finally {
        setBusy(null);
      }
    },
    [onChanged],
  );

  const startEdit = () => {
    if (artifact) {
      setDraft(JSON.stringify(artifact.content, null, 2));
      setChangeNote("");
      setEditing(true);
      setError(null);
      setSuccess(null);
    }
  };

  const saveEdit = async () => {
    if (!artifact) {
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(draft);
    } catch {
      setError("The content is not valid JSON. Fix the syntax and try again.");
      return;
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      setError("The content must be a JSON object.");
      return;
    }
    const ok = await run(
      "save",
      () => editArtifact(artifact.id, parsed as Record<string, unknown>, changeNote),
      "Saved as a new version. It is pending review again.",
    );
    if (ok) {
      setEditing(false);
    }
  };

  const confirmReject = () => {
    if (!artifact) {
      return;
    }
    const reason = window.prompt("Reason for rejecting (optional):", "");
    if (reason === null) {
      return;
    }
    void run("reject", () => rejectArtifact(artifact.id, reason), "Artifact rejected.");
  };

  const isBusy = busy !== null;
  const frozen = isBusy || locked;
  const canApprove =
    artifact !== undefined &&
    (artifact.status === "PENDING_REVIEW" || artifact.status === "REQUIRES_REVIEW");

  const saveSource = async (index: number, source: string): Promise<boolean> => {
    if (!artifact) {
      return false;
    }
    const next = JSON.parse(JSON.stringify(artifact.content)) as typeof artifact.content;
    if (!Array.isArray(next.diagrams) || !next.diagrams[index]) {
      return false;
    }
    next.diagrams[index].plantuml = source;
    return run(
      "save",
      () => editArtifact(artifact.id, next, "PlantUML source edited"),
      "Source saved as a new version. It is pending review again.",
    );
  };

  const showDiff = async (v: ArtifactVersion) => {
    if (!artifact || v.version_number < 2) {
      return;
    }
    try {
      setDiffView(await getArtifactDiff(artifact.id, v.version_number - 1, v.version_number));
    } catch (e) {
      setHistoryError(getArtifactErrorMessage(e));
    }
  };
  const feedbackField = (
    <label className="artifact__feedback">
      <span>Guidance for the AI (optional)</span>
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        rows={2}
        maxLength={4000}
        disabled={isBusy}
      />
    </label>
  );

  return (
    <Card className="artifact">
      <header className="artifact__header">
        <h3 className="artifact__title">{heading}</h3>
        {artifact ? <Badge status={artifact.status} /> : null}
      </header>

      {busy ? <LoadingSpinner label={ACTION_LABEL[busy]} /> : null}
      {error ? <ErrorMessage message={error} /> : null}
      {blockingValidation ? (
        <ValidationPanel
          result={blockingValidation}
          currentVersion={artifact?.current_version ?? 0}
        />
      ) : null}
      {success ? (
        <p className="artifact__success" role="status">
          {success}
        </p>
      ) : null}

      {locked && lockedReason ? (
        <p className="artifact__muted" data-testid="locked-note">
          Read-only: {lockedReason}
        </p>
      ) : null}
      {artifact?.status === "REQUIRES_REVIEW" ? (
        <p className="notice" role="status" data-testid="requires-review">
          An earlier stage changed after this was approved, so the approval is no longer valid.
          Validate it, make any needed edits, and approve it again.
        </p>
      ) : null}
      {artifact === undefined ? (
        <div className="artifact__empty">
          <p>No {heading.toLowerCase()} yet.</p>
          <p className="artifact__muted">Requires: {prerequisite}</p>
          {feedbackField}
          <Button
            disabled={frozen}
            onClick={() =>
              void run(
                "generate",
                () => generateArtifact(projectId, type, feedback),
                "Generated. Review, validate and approve it below.",
              )
            }
          >
            Generate
          </Button>
        </div>
      ) : (
        <>
          <dl className="artifact__facts">
            <div>
              <dt>Artifact ID</dt>
              <dd>
                <code>{artifact.id}</code>
              </dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{artifact.current_version}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{fmt(artifact.created_at)}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{fmt(artifact.updated_at)}</dd>
            </div>
          </dl>

          {editing ? (
            <div className="artifact__editor">
              <p className="artifact__muted">
                Edit the JSON content. Saving creates a new version, re-runs
                validation and returns the artifact to review.
              </p>
              <textarea
                className="artifact__json"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={22}
                spellCheck={false}
                aria-label="Artifact JSON content"
                disabled={isBusy}
              />
              <input
                type="text"
                className="artifact__note"
                placeholder="Change note (optional)"
                value={changeNote}
                onChange={(e) => setChangeNote(e.target.value)}
                maxLength={2000}
                disabled={isBusy}
              />
              <div className="artifact__actions">
                <Button disabled={isBusy} onClick={() => void saveEdit()}>
                  Save new version
                </Button>
                <Button
                  variant="secondary"
                  disabled={isBusy}
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="artifact__content">
                {renderContent(artifact, { onSaveSource: saveSource, disabled: frozen })}
              </div>
              <div className="artifact__actions">
                <Button
                  disabled={frozen || !canApprove}
                  onClick={() =>
                    void run(
                      "approve",
                      () => approveArtifact(artifact.id),
                      "Approved. It can now be used as input for downstream artifacts.",
                    )
                  }
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  disabled={isBusy || artifact.status === "REJECTED"}
                  onClick={confirmReject}
                >
                  Reject
                </Button>
                <Button variant="secondary" disabled={frozen} onClick={startEdit}>
                  Edit
                </Button>
                <Button
                  variant="secondary"
                  disabled={isBusy}
                  onClick={() =>
                    void run(
                      "validate",
                      () => validateArtifact(artifact.id),
                      "Validation complete.",
                    )
                  }
                >
                  Validate
                </Button>
                <Button
                  variant="secondary"
                  disabled={frozen}
                  onClick={() =>
                    void run(
                      "regenerate",
                      () => regenerateArtifact(artifact.id, feedback),
                      "Regenerated as a new version. It is pending review.",
                    )
                  }
                >
                  Regenerate
                </Button>
                <Button
                  variant="secondary"
                  disabled={isBusy}
                  onClick={() =>
                    void run(
                      "critique",
                      () => critiqueArtifact(artifact.id),
                      "AI critique added.",
                    )
                  }
                >
                  AI critique
                </Button>
              </div>
              {feedbackField}
            </>
          )}

          <section className="artifact__section">
            <h4>Source references</h4>
            <p>
              Features:{" "}
              {artifact.source_refs.feature_ids?.length ? (
                artifact.source_refs.feature_ids.map((f) => (
                  <code key={f} className="chip">
                    {f.slice(0, 8)}
                  </code>
                ))
              ) : (
                <span className="artifact__muted">none</span>
              )}
            </p>
            <p>
              Upstream artifacts:{" "}
              {artifact.source_refs.artifacts?.length ? (
                artifact.source_refs.artifacts.map((a) => (
                  <span key={a.artifact_id} className="chip">
                    {a.type} v{a.version}
                  </span>
                ))
              ) : (
                <span className="artifact__muted">none</span>
              )}
            </p>
          </section>

          <section className="artifact__section">
            <h4>Deterministic validation</h4>
            <ValidationPanel
              result={artifact.validation_result}
              currentVersion={artifact.current_version}
            />
          </section>

          {artifact.ai_critique ? (
            <section className="artifact__section">
              <h4>AI critique (advisory, not validation)</h4>
              <p className="artifact__muted">
                Generated by {artifact.ai_critique.model} for version{" "}
                {artifact.ai_critique.content_version}. It does not affect
                approval.
              </p>
              <pre className="code-block">{artifact.ai_critique.text}</pre>
            </section>
          ) : null}

          <section className="artifact__section">
            <Button
              variant="secondary"
              onClick={() => {
                setShowVersions((s) => !s);
                setViewVersion(null);
              }}
            >
              {showVersions ? "Hide history" : "Version history"}
            </Button>
            {showVersions ? (
              <div className="artifact__history">
                {historyLoading ? <LoadingSpinner label="Loading history..." /> : null}
                {historyError ? <ErrorMessage message={historyError} /> : null}
                {!historyLoading && !historyError && versions.length === 0 ? (
                  <p className="artifact__muted">No versions recorded.</p>
                ) : null}
                <ul className="artifact__versions">
                  {versions.map((v) => (
                    <li key={v.id}>
                      <strong>v{v.version_number}</strong> {v.change_type},{" "}
                      {v.status_snapshot}, {fmt(v.created_at)}
                      {v.validation_snapshot
                        ? `, validation ${v.validation_snapshot.status}`
                        : ""}
                      {v.change_note ? ` ("${v.change_note}")` : ""}{" "}
                      <button
                        type="button"
                        className="link-button"
                        onClick={() =>
                          setViewVersion(
                            viewVersion?.id === v.id ? null : v,
                          )
                        }
                      >
                        {viewVersion?.id === v.id ? "hide" : "view"}
                      </button>
                      {v.version_number > 1 ? (
                        <>
                          {" "}
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => void showDiff(v)}
                          >
                            compare with v{v.version_number - 1}
                          </button>
                        </>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {diffView ? (
                  <div>
                    <p className="artifact__muted">
                      v{diffView.from_version} to v{diffView.to_version}: +{diffView.additions} / -
                      {diffView.deletions}
                      {diffView.identical ? " (identical)" : ""}{" "}
                      <button type="button" className="link-button" onClick={() => setDiffView(null)}>
                        close
                      </button>
                    </p>
                    {diffView.identical ? null : <pre className="code-block">{diffView.diff}</pre>}
                  </div>
                ) : null}
                {viewVersion ? (
                  <pre className="code-block">
                    {JSON.stringify(viewVersion.content_snapshot, null, 2)}
                  </pre>
                ) : null}
                {decisions.length > 0 ? (
                  <>
                    <h4>Decisions</h4>
                    <ul className="artifact__versions">
                      {decisions.map((d) => (
                        <li key={d.id}>
                          {d.decision} at v{d.artifact_version}, {fmt(d.created_at)}
                          {d.reason ? `: ${d.reason}` : ""}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </div>
            ) : null}
          </section>
        </>
      )}
    </Card>
  );
}
