import { apiClient } from "./client";
import type { Project, ProjectCreate, ProjectListItem } from "../types/project";
import type { Feature } from "../types/feature";

export async function createProject(data: ProjectCreate): Promise<Project> {
  const response = await apiClient.post<Project>("/projects", data);
  return response.data;
}

export async function listProjects(): Promise<ProjectListItem[]> {
  const response = await apiClient.get<ProjectListItem[]>("/projects");
  return response.data;
}

export async function getProject(id: string): Promise<Project> {
  const response = await apiClient.get<Project>(`/projects/${id}`);
  return response.data;
}

export async function extractFeatures(projectId: string): Promise<Feature[]> {
  const response = await apiClient.post<{ features: Feature[] }>(
    `/projects/${projectId}/extract`,
  );
  return response.data.features;
}
