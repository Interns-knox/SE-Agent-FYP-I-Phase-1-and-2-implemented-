import type { StageKey } from "../../types/workflow";

/** Where each stage lives in the app. */
export function stagePath(projectId: string, key: StageKey): string {
  switch (key) {
    case "FEATURES":
      return `/projects/${projectId}`;
    case "REQUIREMENTS":
      return `/projects/${projectId}/requirements`;
    case "SRS":
      return `/projects/${projectId}/srs`;
    case "ARCHITECTURE":
      return `/projects/${projectId}/architecture`;
    case "UML":
      return `/projects/${projectId}/uml`;
  }
}

export const STAGE_LABEL: Record<StageKey, string> = {
  FEATURES: "Features",
  REQUIREMENTS: "Requirements",
  SRS: "SRS",
  ARCHITECTURE: "Architecture",
  UML: "UML",
};

/** The blocking-message title shown when a stage's prerequisite is not approved. */
export const BLOCK_TITLE: Record<StageKey, string> = {
  FEATURES: "Feature approval required",
  REQUIREMENTS: "Requirements approval required",
  SRS: "SRS approval required",
  ARCHITECTURE: "Architecture approval required",
  UML: "UML approval required",
};

export interface NextAction {
  label: string;
  doneLabel: string;
  next: StageKey | null;
}

/** Bottom-of-page action per stage. */
export const NEXT_ACTION: Partial<Record<StageKey, NextAction>> = {
  REQUIREMENTS: {
    label: "Approve Requirements and Continue to SRS",
    doneLabel: "Continue to SRS",
    next: "SRS",
  },
  SRS: {
    label: "Approve SRS and Continue to Architecture",
    doneLabel: "Continue to Architecture",
    next: "ARCHITECTURE",
  },
  ARCHITECTURE: {
    label: "Approve Architecture and Continue to UML",
    doneLabel: "Continue to UML",
    next: "UML",
  },
  UML: {
    label: "Approve UML and Complete Design",
    doneLabel: "Design complete",
    next: null,
  },
};
