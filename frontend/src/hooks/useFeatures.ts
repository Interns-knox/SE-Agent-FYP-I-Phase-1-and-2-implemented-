import { useCallback, useEffect, useState } from "react";
import { listFeatures } from "../api/features";
import { getErrorMessage } from "../api/client";
import type { Feature, FeatureStatus } from "../types/feature";

export interface UseFeaturesResult {
  data: Feature[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Fetches features for a project, optionally filtered by status.
 * Re-fetches automatically whenever `projectId` or `status` changes.
 */
export function useFeatures(
  projectId: string,
  status?: FeatureStatus,
): UseFeaturesResult {
  const [data, setData] = useState<Feature[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchFeatures = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const features = await listFeatures(projectId, status);
      setData(features);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, status]);

  const refetch = useCallback(() => {
    void fetchFeatures();
  }, [fetchFeatures]);

  useEffect(() => {
    let active = true;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const features = await listFeatures(projectId, status);
        if (active) {
          setData(features);
        }
      } catch (e) {
        if (active) {
          setError(getErrorMessage(e));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void run();
    return () => {
      active = false;
    };
  }, [projectId, status]);

  return { data, loading, error, refetch };
}
