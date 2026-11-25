export type FeatureStatus = "GENERATED" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";

export type ChangeType = "CREATED" | "EDITED" | "STATUS_CHANGE";

export interface Feature {
  id: string;
  project_id: string;
  name: string;
  description: string;
  status: FeatureStatus;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface FeatureVersion {
  id: string;
  feature_id: string;
  version_number: number;
  name_snapshot: string;
  description_snapshot: string;
  change_type: ChangeType;
  created_at: string;
}

export interface FeaturePatch {
  description: string;
}
