import { ArtifactPage } from "../components/artifacts";
import type { PanelSpec } from "../components/artifacts";

const PANELS: PanelSpec[] = [
  {
    type: "DOMAIN_MODEL",
    heading: "Domain Model",
    prerequisite: "an approved Architecture",
  },
  {
    type: "UML_CLASS",
    heading: "Class Diagram",
    prerequisite: "an approved Domain Model",
  },
  {
    type: "UML_SEQUENCE",
    heading: "Sequence Diagrams",
    prerequisite: "an approved Domain Model",
  },
];

export function UmlPage() {
  return (
    <ArtifactPage
      stageKey="UML"
      title="UML Diagrams"
      description="Domain model, class diagram and sequence diagrams, rendered visually from PlantUML and linked to requirements, domain entities and components."
      panels={PANELS}
      tabbed
    />
  );
}
