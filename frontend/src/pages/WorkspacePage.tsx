import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorMessage, LoadingSpinner } from "../components/common";
import {
  ContextPanel,
  ExtractionPanel,
  FeatureList,
} from "../components/workspace";
import { useFeatures } from "../hooks/useFeatures";
import { getProject } from "../api/projects";
import {
  approveFeature,
  patchFeature,
  rejectFeature,
  restoreFeature,
} from "../api/features";
import { getErrorMessage } from "../api/client";
import { FeatureGate } from "../components/workflow/FeatureGate";
import { WorkflowProgress } from "../components/workflow/WorkflowProgress";
import { useWorkflow } from "../hooks/useWorkflow";
import type { Project } from "../types/project";
import type { FeatureStatus } from "../types/feature";
import "../components/artifacts/artifacts.css";
import "./pages.css";

type StatusFilter = "ALL" | FeatureStatus;

interface FilterTab {
  value: StatusFilter;
  label: string;
}

const FILTER_TABS: FilterTab[] = [
  { value: "ALL", label: "All" },
  { value: "GENERATED", label: "Generated" },
  { value: "PENDING_REVIEW", label: "Pending Review" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
];

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";

  const [project, setProject] = useState<Project | null>(null);
  const [projectLoading, setProjectLoading] = useState<boolean>(true);
  const [projectError, setProjectError] = useState<string | null>(null);

  const [selectedFilter, setSelectedFilter] = useState<StatusFilter>("ALL");
  const [actionError, setActionError] = useState<string | null>(null);
  const { data: workflow, loading: workflowLoading, refetch: refetchWorkflow } =
    useWorkflow(projectId);

  const statusForQuery =
    selectedFilter === "ALL" ? undefined : selectedFilter;
  const {
    data: features,
    loading: featuresLoading,
    error: featuresError,
    refetch: refetchFeatures,
  } = useFeatures(projectId, statusForQuery);

  const loadProject = useCallback(async () => {
    if (projectId === "") {
      setProjectError("The requested resource was not found.");
      setProjectLoading(false);
      return;
    }
    setProjectLoading(true);
    setProjectError(null);
    try {
      const result = await getProject(projectId);
      setProject(result);
    } catch (e) {
      setProjectError(getErrorMessage(e));
    } finally {
      setProjectLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    let active = true;

    const run = async () => {
      if (projectId === "") {
        if (active) {
          setProjectError("The requested resource was not found.");
          setProjectLoading(false);
        }
        return;
      }
      try {
        const result = await getProject(projectId);
        if (active) {
          setProject(result);
        }
      } catch (e) {
        if (active) {
          setProjectError(getErrorMessage(e));
        }
      } finally {
        if (active) {
          setProjectLoading(false);
        }
      }
    };

    void run();

    return () => {
      active = false;
    };
  }, [projectId]);

  const runAction = useCallback(
    async (action: () => Promise<unknown>) => {
      setActionError(null);
      try {
        await action();
        refetchFeatures();
        refetchWorkflow();
      } catch (e) {
        setActionError(getErrorMessage(e));
      }
    },
    [refetchFeatures, refetchWorkflow],
  );

  const handleApprove = useCallback(
    (featureId: string) => {
      void runAction(() => approveFeature(featureId));
    },
    [runAction],
  );

  const handleReject = useCallback(
    (featureId: string) => {
      void runAction(() => rejectFeature(featureId));
    },
    [runAction],
  );

  const handleRestore = useCallback(
    (featureId: string) => {
      void runAction(() => restoreFeature(featureId));
    },
    [runAction],
  );

  const handleEdit = useCallback(
    (featureId: string, description: string) => {
      void runAction(() => patchFeature(featureId, { description }));
    },
    [runAction],
  );

  const handleExtractionSuccess = useCallback(() => {
    refetchFeatures();
    refetchWorkflow();
    void loadProject();
  }, [refetchFeatures, refetchWorkflow, loadProject]);

  if (projectLoading) {
    return (
      <div className="page">
        <LoadingSpinner label="Loading project..." />
      </div>
    );
  }

  if (projectError !== null || project === null) {
    return (
      <div className="page">
        <Link to="/" className="page__back">
          ← Back to dashboard
        </Link>
        <ErrorMessage
          message={projectError ?? "The requested resource was not found."}
          onRetry={loadProject}
        />
      </div>
    );
  }

  return (
    <div className="page">
      <Link to="/" className="page__back">
        ← Back to dashboard
      </Link>

      <header className="page__header">
        <div>
          <h1 className="page__title">{project.name}</h1>
          <p className="page__subtitle">{project.description}</p>
          <dl className="workspace__facts">
            <div className="workspace__fact">
              <dt>Stage</dt>
              <dd>{project.stage}</dd>
            </div>
            <div className="workspace__fact">
              <dt>Created</dt>
              <dd>{formatTimestamp(project.created_at)}</dd>
            </div>
            <div className="workspace__fact">
              <dt>Updated</dt>
              <dd>{formatTimestamp(project.updated_at)}</dd>
            </div>
          </dl>
        </div>
      </header>
      <WorkflowProgress projectId={projectId} workflow={workflow} loading={workflowLoading} />
      <section className="workspace__section">
        <h2 className="workspace__section-title">Extraction</h2>
        <ExtractionPanel
          projectId={projectId}
          onSuccess={handleExtractionSuccess}
        />
      </section>

      <section className="workspace__section">
        <h2 className="workspace__section-title">Features</h2>

        <div className="filter-tabs" role="tablist" aria-label="Feature status filter">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={selectedFilter === tab.value}
              className={`filter-tab${
                selectedFilter === tab.value ? " filter-tab--active" : ""
              }`}
              onClick={() => setSelectedFilter(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {actionError ? (
          <div className="page__state">
            <ErrorMessage message={actionError} />
          </div>
        ) : null}

        <FeatureList
          features={features}
          loading={featuresLoading}
          error={featuresError}
          onApprove={handleApprove}
          onReject={handleReject}
          onRestore={handleRestore}
          onEdit={handleEdit}
          onRetry={refetchFeatures}
        />
        <FeatureGate
          projectId={projectId}
          stage={workflow?.stages.find((st) => st.key === "FEATURES") ?? null}
          onRefresh={refetchWorkflow}
        />
      </section>

      <section className="workspace__section">
        <h2 className="workspace__section-title">Context</h2>
        <ContextPanel projectId={projectId} />
      </section>
    </div>
  );
}
