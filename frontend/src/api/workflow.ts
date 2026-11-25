import { apiClient } from "./client";
import type { Workflow } from "../types/workflow";

export async function getWorkflow(projectId: string): Promise<Workflow> {
  return (await apiClient.get<Workflow>(`/projects/${projectId}/workflow`)).data;
}
