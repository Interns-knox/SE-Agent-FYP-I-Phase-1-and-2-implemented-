import { apiClient } from "./client";
import type {
  Feature,
  FeaturePatch,
  FeatureStatus,
  FeatureVersion,
} from "../types/feature";

export async function listFeatures(
  projectId: string,
  status?: FeatureStatus,
): Promise<Feature[]> {
  const response = await apiClient.get<{ features: Feature[] }>(
    `/projects/${projectId}/features`,
    { params: status ? { status } : undefined },
  );
  return response.data.features;
}

export async function patchFeature(
  id: string,
  data: FeaturePatch,
): Promise<Feature> {
  const response = await apiClient.patch<Feature>(`/features/${id}`, data);
  return response.data;
}

export async function approveFeature(id: string): Promise<Feature> {
  const response = await apiClient.post<Feature>(`/features/${id}/approve`);
  return response.data;
}

export async function rejectFeature(id: string): Promise<Feature> {
  const response = await apiClient.post<Feature>(`/features/${id}/reject`);
  return response.data;
}

export async function restoreFeature(id: string): Promise<Feature> {
  const response = await apiClient.post<Feature>(`/features/${id}/restore`);
  return response.data;
}

export async function getFeatureVersions(
  id: string,
): Promise<FeatureVersion[]> {
  const response = await apiClient.get<{ versions: FeatureVersion[] }>(
    `/features/${id}/versions`,
  );
  return response.data.versions;
}
