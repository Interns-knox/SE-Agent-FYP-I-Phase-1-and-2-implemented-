export type StageKey =
  | "FEATURES"
  | "REQUIREMENTS"
  | "SRS"
  | "ARCHITECTURE"
  | "UML";

export type StageStatus =
  | "NOT_STARTED"
  | "IN_PROGRESS"
  | "PENDING_REVIEW"
  | "APPROVED"
  | "BLOCKED"
  | "REQUIRES_REVIEW";

export interface StageArtifactRef {
  id: string;
  type: string;
  status: string;
  version: number;
}

export interface Stage {
  key: StageKey;
  number: number;
  name: string;
  path: string;
  status: StageStatus;
  approval_status: "APPROVED" | "REQUIRES_REVIEW" | "NOT_APPROVED";
  completed: boolean;
  accessible: boolean;
  blocked: boolean;
  required_stage: StageKey | null;
  required_stage_name: string | null;
  blocked_reason: string | null;
  suggested_action: string | null;
  artifacts: StageArtifactRef[];
  missing_artifact_types: string[];
  can_proceed: boolean;
  proceed_blocked_reason: string | null;
  counts?: { total: number; approved: number; pending: number; rejected: number } | null;
  gate_reason?: string | null;
}

export interface Workflow {
  project_id: string;
  current_stage: StageKey;
  complete: boolean;
  stages: Stage[];
}
