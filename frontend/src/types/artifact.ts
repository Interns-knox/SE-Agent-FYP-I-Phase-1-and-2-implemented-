export type ArtifactType =
  | "REQUIREMENTS"
  | "SRS"
  | "ARCHITECTURE"
  | "DOMAIN_MODEL"
  | "UML_CLASS"
  | "UML_SEQUENCE";

export type ArtifactStatus =
  | "PENDING_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "REQUIRES_REVIEW";

export type ArtifactChangeType =
  | "GENERATED"
  | "REGENERATED"
  | "EDITED"
  | "STATUS_CHANGE";

export interface ValidationIssue {
  code: string;
  severity: "error" | "warning";
  message: string;
  path: string;
  suggestion: string;
}

export type ValidationStatus = "PASSED" | "PASSED_WITH_WARNINGS" | "FAILED";

export interface ValidationResult {
  validator: "deterministic";
  status: ValidationStatus;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  checks_run: string[];
  content_version: number | null;
  validated_at: string;
}

export interface AiCritique {
  source: "AI_GENERATED";
  advisory: boolean;
  model: string;
  text: string;
  content_version: number;
  generated_at: string;
}

export interface SourceRefs {
  feature_ids?: string[];
  artifacts?: { artifact_id: string; type: ArtifactType; version: number }[];
}

export interface Artifact {
  id: string;
  project_id: string;
  type: ArtifactType;
  title: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  content: Record<string, any>;
  status: ArtifactStatus;
  current_version: number;
  source_refs: SourceRefs;
  validation_result: ValidationResult | null;
  ai_critique: AiCritique | null;
  created_at: string;
  updated_at: string;
}

export interface ArtifactVersion {
  id: string;
  artifact_id: string;
  version_number: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  content_snapshot: Record<string, any>;
  status_snapshot: ArtifactStatus;
  validation_snapshot: ValidationResult | null;
  change_type: ArtifactChangeType;
  change_note: string | null;
  created_at: string;
}

export interface ArtifactDecision {
  id: string;
  artifact_id: string;
  artifact_version: number;
  decision: string;
  reason: string | null;
  created_at: string;
}

export interface TraceLink {
  id: string;
  owner_artifact_id: string;
  owner_type: ArtifactType;
  owner_status: ArtifactStatus;
  source_kind: string;
  source_ref: string;
  target_kind: string;
  target_ref: string;
  relation: string;
}

export interface Consistency {
  validation: ValidationResult;
  coverage: Record<string, string[]>;
}
