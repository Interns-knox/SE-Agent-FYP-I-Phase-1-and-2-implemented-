import { EmptyState, ErrorMessage, LoadingSpinner } from "../common";
import { FeatureCard } from "./FeatureCard";
import type { Feature } from "../../types/feature";
import "./workspace.css";

export interface FeatureListProps {
  features: Feature[];
  loading: boolean;
  error: string | null;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onRestore: (id: string) => void;
  onEdit: (id: string, description: string) => void;
  onRetry?: () => void;
}

export function FeatureList({
  features,
  loading,
  error,
  onApprove,
  onReject,
  onRestore,
  onEdit,
  onRetry,
}: FeatureListProps) {
  if (loading) {
    return <LoadingSpinner label="Loading features..." />;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={onRetry} />;
  }

  if (features.length === 0) {
    return (
      <EmptyState
        title="No features yet"
        description="Extract features from the project description to get started."
      />
    );
  }

  return (
    <div className="feature-list">
      {features.map((feature) => (
        <FeatureCard
          key={feature.id}
          feature={feature}
          onApprove={onApprove}
          onReject={onReject}
          onRestore={onRestore}
          onEdit={onEdit}
        />
      ))}
    </div>
  );
}
