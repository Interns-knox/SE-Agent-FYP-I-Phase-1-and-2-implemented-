import { useCallback } from "react";
import { Button, ErrorMessage, LoadingSpinner } from "../common";
import { useExtraction } from "../../hooks/useExtraction";
import "./workspace.css";

export interface ExtractionPanelProps {
  projectId: string;
  onSuccess: () => void;
}

export function ExtractionPanel({ projectId, onSuccess }: ExtractionPanelProps) {
  const { extract, loading, error } = useExtraction(projectId);

  const handleExtract = useCallback(async () => {
    const result = await extract();
    if (result !== null) {
      onSuccess();
    }
  }, [extract, onSuccess]);

  return (
    <div className="extraction-panel">
      <div className="extraction-panel__header">
        <Button
          variant="primary"
          disabled={loading}
          onClick={() => {
            void handleExtract();
          }}
        >
          Extract Features
        </Button>
        {loading ? <LoadingSpinner label="Extracting features..." /> : null}
      </div>

      {loading ? (
        <p className="extraction-panel__note">
          This calls the local AI model to analyze the project description and
          may take some time. Please keep this page open while it runs.
        </p>
      ) : null}

      {error ? <ErrorMessage message={error} /> : null}
    </div>
  );
}
