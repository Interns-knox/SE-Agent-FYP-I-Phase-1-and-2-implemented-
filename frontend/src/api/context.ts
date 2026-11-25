import { apiClient } from "./client";
import type { ContextResponse } from "../types/context";

export async function getContext(projectId: string): Promise<ContextResponse> {
  const response = await apiClient.get<ContextResponse>(
    `/projects/${projectId}/context`,
  );
  return response.data;
}
