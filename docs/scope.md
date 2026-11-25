# FYP-I Scope

This repository is the **FYP-I submission** of SE Agent. It contains exactly the deliverables
below. Anything not listed is out of scope and is not implemented here.

## In scope

### Phase 1 — platform, workspace, context, feature extraction

- [x] **Platform architecture** — React + TypeScript frontend, FastAPI backend organized by
  domain, PostgreSQL persistence, Alembic migrations, a replaceable `LLMProvider`
  (Ollama + Qwen3:8B). See [architecture.md](architecture.md).
- [x] **Workspace management** — create, list and open projects; a workspace page per project.
- [x] **Context management** — project context assembled from the stored records
  (`GET /projects/{id}/context`).
- [x] **Feature extraction** — the local model proposes candidate features from the project
  description; output is parsed, validated and de-duplicated.
- [x] **Human editing and approval** — edit, approve, reject and restore features, with a full
  version history and a decision audit trail.

### Phase 2 — requirements, validation, domain modeling, PlantUML, traceability

- [x] **Requirements generation** — functional requirements (`FR-###`) and non-functional
  requirements (`NFR-###`) with the fields described in the README. Identifiers are assigned by
  the backend and are unique, stable and never reused.
- [x] **Human validation** — deterministic backend validation (errors, warnings, suggestions),
  an advisory AI critique, and edit / approve / reject with versions and history.
- [x] **Domain modeling** — a conceptual domain model with entities, attributes, relationships,
  cardinalities and business rules.
- [x] **PlantUML generation and visual rendering** — class and sequence diagrams and the domain
  model diagram, rendered locally as SVG with pan and zoom, source view and source editing.
- [x] **Traceability** — links between features, requirements, architecture components, domain
  entities and UML diagrams; dangling-reference and coverage checks.
- [x] **Supporting artifacts in the guided workflow** — the SRS and the system architecture are
  generated and approved between requirements and UML, and the guided workflow with approval
  gates (including `REQUIRES_REVIEW` handling for stale approvals) controls the order.

## Platform persistence (not a deliverable)

PostgreSQL stores SE Agent's *own* data only: projects, features, feature versions, user
decisions, artifacts, artifact versions, approval decisions and traceability links
(eight tables, migrations `0001` and `0002`). This is required for workspaces, versioning,
approval history and traceability to work.

The submission does **not** include a database-design deliverable and does **not** generate a
database for any target application: there is no database-design artifact, page, generator or
endpoint.

## Out of scope (not in this repository)

- Generation of application source code, tests or project scaffolding.
- Execution of generated artifacts, containers or sandboxes.
- Impact analysis and selective regeneration.
- Evaluation dashboards and benchmarking, CI/CD and deployment.
- Database design for target applications.
- Authentication, multi-user collaboration and multi-tenant operation.

## Honesty rules

- Features are either genuinely working end to end or not present.
- No quality or performance numbers are claimed unless they were measured.
- Model output is always a candidate; nothing is treated as approved until a person approves it
  and the deterministic checks pass.
