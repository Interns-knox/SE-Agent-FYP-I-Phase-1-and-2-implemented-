import { useCallback, useEffect, useState } from "react";
import { listProjects } from "../api/projects";
import { getErrorMessage } from "../api/client";
import type { ProjectListItem } from "../types/project";

export interface UseProjectsResult {
  data: ProjectListItem[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Fetches the list of projects on mount and exposes loading/error state
 * along with a `refetch` callback to re-run the request on demand.
 */
export function useProjects(): UseProjectsResult {
  const [data, setData] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const projects = await listProjects();
      setData(projects);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const refetch = useCallback(() => {
    void fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    let active = true;
    const run = async () => {
      try {
        const projects = await listProjects();
        if (active) {
          setData(projects);
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
  }, []);

  return { data, loading, error, refetch };
}
