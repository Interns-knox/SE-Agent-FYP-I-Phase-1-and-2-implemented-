import { ArtifactPage } from "../components/artifacts";
import type { PanelSpec } from "../components/artifacts";

const PANELS: PanelSpec[] = [
  {
    type: "REQUIREMENTS",
    heading: "Requirements",
    prerequisite: "at least one approved feature",
  },
];

export function RequirementsPage() {
  return (
    <ArtifactPage
      stageKey="REQUIREMENTS"
      title="Requirements"
      description="Structured functional and non-functional requirements derived from approved features."
      panels={PANELS}
    />
  );
}
