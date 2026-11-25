import { Link, useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  LoadingSpinner,
} from "../components/common";
import { useProjects } from "../hooks/useProjects";
import type { FeatureCountSummary, ProjectListItem } from "../types/project";
import "./pages.css";

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

interface CountChip {
  key: keyof FeatureCountSummary;
  label: string;
  className: string;
}

const COUNT_CHIPS: CountChip[] = [
  { key: "GENERATED", label: "Generated", className: "count-chip--generated" },
  {
    key: "PENDING_REVIEW",
    label: "Pending",
    className: "count-chip--pending",
  },
  { key: "APPROVED", label: "Approved", className: "count-chip--approved" },
  { key: "REJECTED", label: "Rejected", className: "count-chip--rejected" },
];

function ProjectCard({
  project,
  onOpen,
}: {
  project: ProjectListItem;
  onOpen: (id: string) => void;
}) {
  return (
    <Card className="project-card" onClick={() => onOpen(project.id)}>
      <div className="project-card__header">
        <h2 className="project-card__name">{project.name}</h2>
        <span className="project-card__stage">{project.stage}</span>
      </div>

      <p className="project-card__description">{project.description}</p>

      <div className="project-card__counts">
        {COUNT_CHIPS.map((chip) => (
          <span key={chip.key} className={`count-chip ${chip.className}`}>
            {chip.label}: {project.feature_counts[chip.key]}
          </span>
        ))}
      </div>

      <div className="project-card__timestamps">
        <span>Created: {formatTimestamp(project.created_at)}</span>
        <span>Updated: {formatTimestamp(project.updated_at)}</span>
      </div>
    </Card>
  );
}

export function DashboardPage() {
  const { data, loading, error, refetch } = useProjects();
  const navigate = useNavigate();

  const openProject = (id: string) => {
    navigate(`/projects/${id}`);
  };

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1 className="page__title">SE Agent</h1>
          <p className="page__subtitle">
            Your projects and their feature extraction progress.
          </p>
        </div>
        <Link to="/projects/new">
          <Button variant="primary">New Project</Button>
        </Link>
      </header>

      {loading ? (
        <div className="page__state">
          <LoadingSpinner label="Loading projects..." />
        </div>
      ) : null}

      {!loading && error ? (
        <div className="page__state">
          <ErrorMessage message={error} onRetry={refetch} />
        </div>
      ) : null}

      {!loading && !error && data.length === 0 ? (
        <div className="page__state">
          <EmptyState
            title="No projects yet"
            description="Create your first project to start extracting features from a description."
            action={
              <Link to="/projects/new">
                <Button variant="primary">New Project</Button>
              </Link>
            }
          />
        </div>
      ) : null}

      {!loading && !error && data.length > 0 ? (
        <div className="dashboard__grid">
          {data.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onOpen={openProject}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
