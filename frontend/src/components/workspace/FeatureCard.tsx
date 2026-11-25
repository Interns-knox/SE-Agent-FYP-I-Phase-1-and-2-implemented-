import { useCallback, useState } from "react";
import {
  Badge,
  Button,
  Card,
  ErrorMessage,
  LoadingSpinner,
} from "../common";
import { getFeatureVersions } from "../../api/features";
import { getErrorMessage } from "../../api/client";
import type { Feature, FeatureVersion } from "../../types/feature";
import "./workspace.css";

export interface FeatureCardProps {
  feature: Feature;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onRestore: (id: string) => void;
  onEdit: (id: string, description: string) => void;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

const CHANGE_TYPE_LABEL: Record<FeatureVersion["change_type"], string> = {
  CREATED: "Created",
  EDITED: "Edited",
  STATUS_CHANGE: "Status change",
};

export function FeatureCard({
  feature,
  onApprove,
  onReject,
  onRestore,
  onEdit,
}: FeatureCardProps) {
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [draft, setDraft] = useState<string>(feature.description);

  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [versions, setVersions] = useState<FeatureVersion[] | null>(null);
  const [versionsLoading, setVersionsLoading] = useState<boolean>(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);

  const isRejected = feature.status === "REJECTED";
  const isApproved = feature.status === "APPROVED";
  const canReview =
    feature.status === "PENDING_REVIEW" || feature.status === "GENERATED";

  const startEditing = useCallback(() => {
    setDraft(feature.description);
    setIsEditing(true);
  }, [feature.description]);

  const cancelEditing = useCallback(() => {
    setDraft(feature.description);
    setIsEditing(false);
  }, [feature.description]);

  const trimmedDraft = draft.trim();
  const saveDisabled =
    trimmedDraft.length === 0 || trimmedDraft === feature.description.trim();

  const saveEdit = useCallback(() => {
    if (saveDisabled) {
      return;
    }
    onEdit(feature.id, trimmedDraft);
    setIsEditing(false);
  }, [saveDisabled, onEdit, feature.id, trimmedDraft]);

  const loadVersions = useCallback(async () => {
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      const result = await getFeatureVersions(feature.id);
      setVersions(result);
    } catch (e) {
      setVersionsError(getErrorMessage(e));
    } finally {
      setVersionsLoading(false);
    }
  }, [feature.id]);

  const toggleHistory = useCallback(() => {
    const next = !historyOpen;
    setHistoryOpen(next);
    if (next && versions === null && !versionsLoading) {
      void loadVersions();
    }
  }, [historyOpen, versions, versionsLoading, loadVersions]);

  const cardClassName = isRejected
    ? "feature-card feature-card--rejected"
    : "feature-card";

  return (
    <Card className={cardClassName}>
      <div className="feature-card__header">
        <h3 className="feature-card__name">{feature.name}</h3>
        <div className="feature-card__meta">
          <Badge status={feature.status} />
          <span className="feature-card__version">
            v{feature.current_version}
          </span>
        </div>
      </div>

      {isEditing ? (
        <div className="feature-card__edit">
          <textarea
            className="feature-card__textarea"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={4}
            aria-label="Feature description"
          />
          <div className="feature-card__edit-actions">
            <Button variant="primary" disabled={saveDisabled} onClick={saveEdit}>
              Save
            </Button>
            <Button variant="secondary" onClick={cancelEditing}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <p className="feature-card__description">{feature.description}</p>
      )}

      {!isEditing ? (
        <div className="feature-card__actions">
          <Button variant="secondary" onClick={startEditing}>
            Edit
          </Button>

          {canReview ? (
            <>
              <Button variant="primary" onClick={() => onApprove(feature.id)}>
                Approve
              </Button>
              <Button variant="danger" onClick={() => onReject(feature.id)}>
                Reject
              </Button>
            </>
          ) : null}

          {isRejected ? (
            <Button variant="secondary" onClick={() => onRestore(feature.id)}>
              Restore
            </Button>
          ) : null}

          {isApproved ? (
            <span className="feature-card__approved" aria-label="Feature approved">
              ✓ Approved
            </span>
          ) : null}

          <Button variant="secondary" onClick={toggleHistory}>
            {historyOpen ? "Hide history" : "History"}
          </Button>
        </div>
      ) : null}

      {historyOpen ? (
        <div className="feature-card__history">
          {versionsLoading ? <LoadingSpinner label="Loading history..." /> : null}
          {versionsError ? (
            <ErrorMessage message={versionsError} onRetry={loadVersions} />
          ) : null}
          {!versionsLoading && !versionsError && versions ? (
            versions.length === 0 ? (
              <p className="feature-card__history-empty">No version history.</p>
            ) : (
              <ul className="feature-card__history-list">
                {versions.map((version) => (
                  <li key={version.id} className="feature-card__history-item">
                    <div className="feature-card__history-head">
                      <span className="feature-card__history-version">
                        v{version.version_number}
                      </span>
                      <span className="feature-card__history-type">
                        {CHANGE_TYPE_LABEL[version.change_type]}
                      </span>
                      <span className="feature-card__history-date">
                        {formatTimestamp(version.created_at)}
                      </span>
                    </div>
                    <p className="feature-card__history-snapshot">
                      {version.description_snapshot}
                    </p>
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
