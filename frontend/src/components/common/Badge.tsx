import type { ArtifactStatus } from "../../types/artifact";
import type { FeatureStatus } from "../../types/feature";

type AnyStatus = FeatureStatus | ArtifactStatus;
import "./common.css";

export interface BadgeProps {
  status: AnyStatus;
}

const STATUS_CLASS: Record<AnyStatus, string> = {
  GENERATED: "badge--generated",
  PENDING_REVIEW: "badge--pending",
  APPROVED: "badge--approved",
  REJECTED: "badge--rejected",
  REQUIRES_REVIEW: "badge--pending",
};

const STATUS_LABEL: Record<AnyStatus, string> = {
  GENERATED: "Generated",
  PENDING_REVIEW: "Pending Review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  REQUIRES_REVIEW: "Requires Review",
};

export function Badge({ status }: BadgeProps) {
  return (
    <span
      className={`badge ${STATUS_CLASS[status]}`}
      aria-label={`status: ${status}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}
