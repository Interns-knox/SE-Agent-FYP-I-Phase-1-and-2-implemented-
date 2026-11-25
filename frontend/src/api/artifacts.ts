import { isAxiosError } from "axios";
import { apiClient, getErrorMessage } from "./client";
import type {
  Artifact,
  ArtifactDecision,
  ArtifactType,
  ArtifactVersion,
  Consistency,
  TraceLink,
  ValidationResult,
} from "../types/artifact";

export async function listArtifacts(projectId: string): Promise<Artifact[]> {
  const r = await apiClient.get<{ artifacts: Artifact[] }>(
    `/projects/${projectId}/artifacts`,
  );
  return r.data.artifacts;
}

export async function generateArtifact(
  projectId: string,
  type: ArtifactType,
  feedback?: string,
): Promise<Artifact> {
  const r = await apiClient.post<Artifact>(
    `/projects/${projectId}/artifacts/generate`,
    { type, feedback: feedback || null },
  );
  return r.data;
}

export async function regenerateArtifact(
  id: string,
  feedback?: string,
): Promise<Artifact> {
  const r = await apiClient.post<Artifact>(`/artifacts/${id}/regenerate`, {
    feedback: feedback || null,
  });
  return r.data;
}

export async function editArtifact(
  id: string,
  content: Record<string, unknown>,
  changeNote?: string,
): Promise<Artifact> {
  const r = await apiClient.put<Artifact>(`/artifacts/${id}`, {
    content,
    change_note: changeNote || null,
  });
  return r.data;
}

export async function validateArtifact(id: string): Promise<Artifact> {
  const r = await apiClient.post<Artifact>(`/artifacts/${id}/validate`);
  return r.data;
}

export async function approveArtifact(id: string): Promise<Artifact> {
  const r = await apiClient.post<Artifact>(`/artifacts/${id}/approve`);
  return r.data;
}

export async function rejectArtifact(
  id: string,
  reason?: string,
): Promise<Artifact> {
  const r = await apiClient.post<Artifact>(`/artifacts/${id}/reject`, {
    reason: reason || null,
  });
  return r.data;
}

export async function critiqueArtifact(id: string): Promise<Artifact> {
  const r = await apiClient.post<Artifact>(`/artifacts/${id}/critique`);
  return r.data;
}

export async function getArtifactVersions(
  id: string,
): Promise<ArtifactVersion[]> {
  const r = await apiClient.get<{ versions: ArtifactVersion[] }>(
    `/artifacts/${id}/versions`,
  );
  return r.data.versions;
}

export async function getArtifactDecisions(
  id: string,
): Promise<ArtifactDecision[]> {
  const r = await apiClient.get<{ decisions: ArtifactDecision[] }>(
    `/artifacts/${id}/decisions`,
  );
  return r.data.decisions;
}

export async function getDependencies(projectId: string): Promise<TraceLink[]> {
  const r = await apiClient.get<{ links: TraceLink[] }>(
    `/projects/${projectId}/dependencies`,
  );
  return r.data.links;
}

export async function getConsistency(projectId: string): Promise<Consistency> {
  const r = await apiClient.get<Consistency>(
    `/projects/${projectId}/consistency`,
  );
  return r.data;
}

/**
 * Artifact endpoints return actionable `detail` messages (for example
 * "An approved REQUIREMENTS artifact is required first."). Show those instead
 * of the generic per-status text. Falls back to the shared friendly message.
 */
export function getArtifactErrorMessage(error: unknown): string {
  if (isAxiosError(error) && error.response) {
    const detail = (error.response.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string" && error.response.status < 500) {
      return detail;
    }
    if (
      detail !== null &&
      typeof detail === "object" &&
      "blocked" in detail &&
      typeof (detail as { reason?: unknown }).reason === "string"
    ) {
      const d = detail as unknown as { message?: string; reason: string; suggested_action?: string };
      return [d.message, d.reason, d.suggested_action].filter(Boolean).join(". ");
    }
    if (
      detail !== null &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof (detail as { message: unknown }).message === "string"
    ) {
      return (detail as { message: string }).message;
    }
  }
  return getErrorMessage(error);
}

/** Validation result embedded in a failed approval response, if any. */
export function getEmbeddedValidation(error: unknown): ValidationResult | null {
  if (isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (detail !== null && typeof detail === "object" && "validation" in detail) {
      return (detail as { validation: ValidationResult }).validation;
    }
  }
  return null;
}

export interface ArtifactDiff {
  artifact_id: string;
  from_version: number;
  to_version: number;
  identical: boolean;
  additions: number;
  deletions: number;
  diff: string;
}

export async function getArtifactDiff(
  id: string,
  fromVersion: number,
  toVersion: number,
): Promise<ArtifactDiff> {
  return (
    await apiClient.get<ArtifactDiff>(`/artifacts/${id}/diff`, {
      params: { from_version: fromVersion, to_version: toVersion },
    })
  ).data;
}

export interface RenderResult {
  ok: boolean;
  svg: string | null;
  error: string | null;
  line: number | null;
  renderer_available: boolean;
  cached: boolean;
}

/** Validates and renders PlantUML source locally on the backend. */
export async function renderPlantUml(source: string): Promise<RenderResult> {
  return (await apiClient.post<RenderResult>("/uml/render", { source })).data;
}
