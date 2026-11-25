import { ArtifactPage } from "../components/artifacts";
import type { PanelSpec } from "../components/artifacts";

const PANELS: PanelSpec[] = [
  {
    type: "ARCHITECTURE",
    heading: "Architecture",
    prerequisite: "an approved SRS",
  },
];

export function ArchitecturePage() {
  return (
    <ArtifactPage
      stageKey="ARCHITECTURE"
      title="System Architecture"
      description="Components, responsibilities and dependencies, allocated to requirements."
      panels={PANELS}
    />
  );
}
