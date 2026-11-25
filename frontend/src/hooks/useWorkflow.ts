import { useCallback, useEffect, useState } from "react";
import { getArtifactErrorMessage } from "../api/artifacts";
import { getWorkflow } from "../api/workflow";
import type { Workflow } from "../types/workflow";

export interface UseWorkflowResult {
  data: Workflow | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Stage-by-stage workflow state for a project; call `refetch` after any state change. */
export function useWorkflow(projectId: string): UseWorkflowResult {
  const [data, setData] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState<number>(0);

  useEffect(() => {
    let active = true;
    const run = async () => {
      try {
        const wf = await getWorkflow(projectId);
        if (active) {
          setData(wf);
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
