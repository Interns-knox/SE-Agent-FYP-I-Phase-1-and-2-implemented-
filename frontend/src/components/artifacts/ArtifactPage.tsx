import { useCallback, useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useArtifacts } from "../../hooks/useArtifacts";
import { useWorkflow } from "../../hooks/useWorkflow";
import type { Artifact, ArtifactType } from "../../types/artifact";
import type { StageKey } from "../../types/workflow";
import { Badge, Button, ErrorMessage, LoadingSpinner } from "../common";
import { BlockedStage } from "../workflow/BlockedStage";
import { StageActions } from "../workflow/StageActions";
import { WorkflowProgress } from "../workflow/WorkflowProgress";
import { ArtifactPanel } from "./ArtifactPanel";
import { TraceabilityPanel } from "./TraceabilityPanel";
import "../../pages/pages.css";
import "./artifacts.css";

export interface PanelSpec {
  type: ArtifactType;
  heading: string;
  prerequisite: string;
}

export interface ArtifactPageProps {
  stageKey: StageKey;
  title: string;
  description: string;
  panels: PanelSpec[];
  /** Show the panels as tabs (UML: domain model, class diagram, sequence diagrams). */
  tabbed?: boolean;
  children?: ReactNode;
}

const NEEDS_DOMAIN: ArtifactType[] = ["UML_CLASS", "UML_SEQUENCE"];

/** Shared shell for the design stage screens: progress, gate, artifacts, next action. */
export function ArtifactPage({
  stageKey,
  title,
  description,
  panels,
  tabbed = false,
  children,
}: ArtifactPageProps) {
  const { id } = useParams<{ id: string }>();
  const projectId = id ?? "";
  const art = useArtifacts(projectId);
  const wf = useWorkflow(projectId);
  const [refreshKey, setRefreshKey] = useState<number>(0);
  const [activeTab, setActiveTab] = useState<ArtifactType | null>(null);
  const { refetch: refetchArtifacts } = art;
  const { refetch: refetchWorkflow } = wf;

  const onChanged = useCallback(() => {
    refetchArtifacts();
    refetchWorkflow();
    setRefreshKey((k) => k + 1);
  }, [refetchArtifacts, refetchWorkflow]);

  const stage = wf.data?.stages.find((s) => s.key === stageKey) ?? null;
  const byType = (t: ArtifactType): Artifact | undefined => art.data.find((a) => a.type === t);
  const domainApproved = byType("DOMAIN_MODEL")?.status === "APPROVED";
  const ready = !art.loading && !wf.loading && !art.error && !wf.error && stage !== null;

  const lockFor = (type: ArtifactType): string | null => {
    if (stage?.blocked) {
      return stage.blocked_reason;
    }
    if (NEEDS_DOMAIN.includes(type) && !domainApproved) {
      return "The domain model must be approved before class and sequence diagrams can be changed.";
    }
    return null;
  };

  // A locked stage still shows artifacts that already exist, but never an empty generator.
  const visible = panels.filter((p) => !stage?.blocked || byType(p.type) !== undefined);
  const current =
    visible.find((p) => p.type === activeTab) ??
    visible.find((p) => byType(p.type)?.status !== "APPROVED") ??
    visible[0];
  const shown = tabbed ? (current ? [current] : []) : visible;

  return (
    <div className="page">
      <Link to={`/projects/${projectId}`} className="page__back">
        ← Back to workspace
      </Link>
      <WorkflowProgress projectId={projectId} workflow={wf.data} loading={wf.loading} />
      <header className="page__header">
        <div>
          <h1 className="page__title">{title}</h1>
          <p className="page__subtitle">{description}</p>
        </div>
      </header>
      {art.loading || wf.loading ? <LoadingSpinner label="Loading..." /> : null}
      {art.error ? <ErrorMessage message={art.error} onRetry={art.refetch} /> : null}
      {wf.error ? <ErrorMessage message={wf.error} onRetry={wf.refetch} /> : null}

      {ready && stage?.blocked ? <BlockedStage stage={stage} projectId={projectId} /> : null}

      {ready && tabbed ? (
        <div className="artifact-tabs" role="tablist" aria-label={`${title} artifacts`}>
          {visible.map((p) => {
            const a = byType(p.type);
            return (
              <button
                key={p.type}
                type="button"
                role="tab"
                aria-selected={current?.type === p.type}
                className={`artifact-tab${current?.type === p.type ? " artifact-tab--active" : ""}`}
                onClick={() => setActiveTab(p.type)}
              >
                {p.heading} {a ? <Badge status={a.status} /> : <span className="artifact__muted">not generated</span>}
              </button>
            );
          })}
        </div>
      ) : null}

      {ready
        ? shown.map((p) => {
            const reason = lockFor(p.type);
            const domainBlocked = !stage?.blocked && NEEDS_DOMAIN.includes(p.type) && !domainApproved;
            return (
              <div key={p.type}>
                {domainBlocked && !byType(p.type) ? (
                  <section className="wf-blocked" role="alert" aria-label="Domain model approval required">
                    <h2 className="wf-blocked__title">Domain model approval required</h2>
                    <p>
                      Class and sequence diagrams are derived from the domain model. Generate and
                      approve the domain model before generating {p.heading.toLowerCase()}.
                    </p>
                    <Button onClick={() => setActiveTab("DOMAIN_MODEL")}>Back to Domain Model</Button>
                  </section>
                ) : (
                  <ArtifactPanel
                    projectId={projectId}
                    type={p.type}
                    heading={p.heading}
                    prerequisite={p.prerequisite}
                    artifact={byType(p.type)}
                    onChanged={onChanged}
                    locked={reason !== null}
                    lockedReason={reason}
                  />
                )}
              </div>
            );
          })
        : null}
      {children}
      {ready && stage ? (
        <StageActions
          projectId={projectId}
          stageKey={stageKey}
          stage={stage}
          artifacts={art.data}
          onChanged={onChanged}
        />
      ) : null}
      {ready ? <TraceabilityPanel projectId={projectId} refreshKey={refreshKey} /> : null}
    </div>
  );
}
