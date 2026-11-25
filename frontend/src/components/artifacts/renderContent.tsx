import type { Artifact } from "../../types/artifact";
import { DomainModelView, UmlDiagramsView } from "./UmlViews";
import { ArchitectureView, RequirementsView, SrsView } from "./viewers";

export interface RenderOptions {
  /** Saves edited PlantUML source of diagram `index` as a new artifact version. */
  onSaveSource?: (diagramIndex: number, source: string) => Promise<boolean>;
  disabled?: boolean;
}

export function renderContent(
  artifact: Pick<Artifact, "type" | "content">,
  opts: RenderOptions = {},
) {
  switch (artifact.type) {
    case "REQUIREMENTS":
      return <RequirementsView content={artifact.content} />;
    case "SRS":
      return <SrsView content={artifact.content} />;
    case "ARCHITECTURE":
      return <ArchitectureView content={artifact.content} />;
    case "DOMAIN_MODEL":
      return <DomainModelView content={artifact.content} {...opts} />;
    case "UML_CLASS":
    case "UML_SEQUENCE":
      return <UmlDiagramsView content={artifact.content} {...opts} />;
  }
}
