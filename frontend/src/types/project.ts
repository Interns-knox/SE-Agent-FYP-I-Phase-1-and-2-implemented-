export type ProjectStatus = "ACTIVE" | "ARCHIVED";

export type ProjectStage = "CREATED" | "EXTRACTION_DONE";

export interface FeatureCountSummary {
  GENERATED: number;
  PENDING_REVIEW: number;
  APPROVED: number;
  REJECTED: number;
}

export interface ProjectCreate {
  name: string;
  description: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  stage: ProjectStage;
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem extends Project {
  feature_counts: FeatureCountSummary;
}
