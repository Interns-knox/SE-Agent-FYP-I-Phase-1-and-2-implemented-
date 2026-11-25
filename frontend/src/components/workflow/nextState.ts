import type { Artifact, ArtifactType } from "../../types/artifact";
import type { Stage, StageKey } from "../../types/workflow";

export const STAGE_TYPES: Record<string, ArtifactType[]> = {
  REQUIREMENTS: ["REQUIREMENTS"],
  SRS: ["SRS"],
  ARCHITECTURE: ["ARCHITECTURE"],
  UML: ["DOMAIN_MODEL", "UML_CLASS", "UML_SEQUENCE"],
};

const NAMES: Record<ArtifactType, string> = {
  REQUIREMENTS: "Requirements",
  SRS: "SRS",
  ARCHITECTURE: "Architecture",
  DOMAIN_MODEL: "Domain Model",
  UML_CLASS: "Class Diagram",
  UML_SEQUENCE: "Sequence Diagrams",
};

export interface NextState {
  enabled: boolean;
  approved: boolean;
  reason: string | null;
}

/** Whether the "approve and continue" action may run, and why not. Pure, for testing. */
export function computeNextState(
  stage: Stage,
  stageKey: StageKey,
  artifacts: Artifact[],
): NextState {
  const types = STAGE_TYPES[stageKey] ?? [];
  const items = types.map((t) => ({ t, a: artifacts.find((x) => x.type === t) }));
  if (stage.blocked) {
    return { enabled: false, approved: false, reason: stage.blocked_reason };
  }
  const missing = items.filter((i) => !i.a).map((i) => NAMES[i.t]);
  if (missing.length > 0) {
    return { enabled: false, approved: false, reason: `Generate first: ${missing.join(", ")}.` };
  }
  const present = items.map((i) => i.a as Artifact);
  const rejected = present.filter((a) => a.status === "REJECTED");
  if (rejected.length > 0) {
    return {
      enabled: false,
      approved: false,
      reason: `${NAMES[rejected[0].type]} was rejected. Edit or regenerate it before approving.`,
    };
  }
  if (stage.completed) {
    return { enabled: true, approved: true, reason: null };
  }
  const failed = present.filter((a) => a.validation_result?.status === "FAILED");
  if (failed.length > 0) {
    return {
      enabled: false,
      approved: false,
      reason: `${NAMES[failed[0].type]} has validation errors. Fix them and validate again before approving.`,
    };
  }
  return { enabled: true, approved: false, reason: null };
}
