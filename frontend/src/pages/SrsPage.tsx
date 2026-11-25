import { ArtifactPage } from "../components/artifacts";
import type { PanelSpec } from "../components/artifacts";

const PANELS: PanelSpec[] = [
  {
    type: "SRS",
    heading: "SRS",
    prerequisite: "an approved Requirements artifact",
  },
];

export function SrsPage() {
  return (
    <ArtifactPage
      stageKey="SRS"
      title="Software Requirements Specification"
      description="SRS assembled from approved requirements plus AI-written narrative sections."
      panels={PANELS}
    />
  );
}
