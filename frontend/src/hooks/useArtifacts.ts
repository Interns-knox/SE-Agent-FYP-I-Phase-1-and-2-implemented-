import { useCallback, useEffect, useState } from "react";
import { listArtifacts } from "../api/artifacts";
import { getArtifactErrorMessage } from "../api/artifacts";
import type { Artifact } from "../types/artifact";

export interface UseArtifactsResult {
  data: Artifact[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Loads every artifact of a project; re-fetches when `refetch` is called. */
export function useArtifacts(projectId: string): UseArtifactsResult {
  const [data, setData] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState<number>(0);

  useEffect(() => {
    let active = true;
    const run = async () => {
      try {
        const items = await listArtifacts(projectId);
        if (active) {
          setData(items);
          setError(null);
        }
      } catch (e) {
        if (active) {
          setError(getArtifactErrorMessage(e));
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
  }, [projectId, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, refetch };
}
