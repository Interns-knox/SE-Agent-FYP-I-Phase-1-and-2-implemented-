import type { Project } from "./project";
import type { Feature, FeatureStatus } from "./feature";

export interface FeatureSummary {
  id: string;
  name: string;
  status: FeatureStatus;
  current_version: number;
}

export interface ContextResponse {
  project: Project;
  approved_features: Feature[];
  all_features_summary: FeatureSummary[];
  last_extraction_at: string | null;
}
