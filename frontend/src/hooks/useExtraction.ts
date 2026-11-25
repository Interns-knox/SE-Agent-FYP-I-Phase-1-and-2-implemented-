import { useCallback, useState } from "react";
import { extractFeatures } from "../api/projects";
import { getErrorMessage } from "../api/client";
import type { Feature } from "../types/feature";

export interface UseExtractionResult {
  extract: () => Promise<Feature[] | null>;
  loading: boolean;
  error: string | null;
}

/**
 * Triggers feature extraction for a project.
 *
 * `extract` resolves with the extracted features on success, or `null` on
 * failure (in which case `error` holds a user-friendly message).
 */
export function useExtraction(projectId: string): UseExtractionResult {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const extract = useCallback(async (): Promise<Feature[] | null> => {
    setLoading(true);
    setError(null);
    try {
      return await extractFeatures(projectId);
    } catch (e) {
      setError(getErrorMessage(e));
      return null;
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  return { extract, loading, error };
}
