# SE Agent — Architecture (FYP-I)

This document describes the architecture of the FYP-I submission: the components, how data flows
between them, the platform's persistence schema and the key design decisions. Scope is defined in
[scope.md](scope.md).

---

## System overview

SE Agent is a full-stack web application with four runtime pieces:

1. A **React + TypeScript** single-page frontend.
2. A **FastAPI** backend that exposes a REST API, holds the domain logic and persists to
   PostgreSQL.
3. A locally hosted **LLM** (Ollama serving Qwen3:8B) that the backend calls to *propose*
   features, requirements, the SRS, the architecture, the domain model and UML diagrams.
4. A locally installed **PlantUML** command that the backend uses to check UML syntax and to
   render diagrams to SVG.

The human engineer is in control throughout. The model only produces candidates; deterministic
backend validators check them; a person approves or rejects them; and every change is versioned.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Frontend (React 19 + TypeScript + Vite)                                       │
│   pages ─► hooks ({data,loading,error,refetch}) ─► api/ (axios)               │
│   workflow progress · feature gate · artifact panels · diagram viewer         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / JSON
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ Backend (FastAPI)                                                             │
│   routers ─► services ─► SQLAlchemy ORM ─► PostgreSQL (platform tables)      │
│                 │                                                              │
│                 ├─ workflow   stage status, approval gates, stale approvals   │
│                 ├─ artifacts  generation, validators, versions, traceability  │
│                 ├─ ai         LLMProvider ─► Ollama ─► Qwen3:8B               │
│                 └─ uml_render PlantUML (local process): syntax check + SVG    │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Backend domain modules

Modules live under `backend/app/domains/`. Each has `router.py` (HTTP), `schemas.py` (Pydantic
models), `service.py` (logic) and, if it owns data, `models.py` (SQLAlchemy).

| Domain | Responsibility |
| --- | --- |
| `workspace` | Projects: create, list with feature counts, retrieve, stage transitions, and the extraction entry point. |
| `features` | Feature lifecycle: creation from extraction, listing, edit, approve, reject, restore, version history, decision audit. Notifies the workflow when features change. |
| `context` | Builds the structured project context from existing records (no state of its own). |
| `ai` | `LLMProvider` abstraction, `OllamaProvider`, extraction schemas and `FeatureExtractionService` (tolerant JSON parsing, retry, de-duplication). |
| `artifacts` | The six artifact types (requirements, SRS, architecture, domain model, UML class, UML sequence): prompts, generation, requirement-id assignment, domain-model normalization, deterministic validators, versions, decisions, diffs, trace-link derivation, consistency check, PlantUML rendering. |
| `workflow` | The five stages, their status, the prerequisite gates enforced by the artifact endpoints, and the invalidation of downstream approvals. |

`backend/app/main.py` builds the application with `create_app()`: CORS from `CORS_ORIGINS`, the
routers of every domain and a global handler that returns a generic 500 body (no tracebacks).

---

## Guided workflow and approval gates

```
Features → Requirements → SRS → Architecture → UML (domain model, class, sequence)
```

- A stage's **status** is computed on request from the stored features and artifacts:
  `NOT_STARTED`, `IN_PROGRESS`, `PENDING_REVIEW`, `APPROVED`, `BLOCKED`, `REQUIRES_REVIEW`.
- A stage is **effectively approved** only if its artifacts are `APPROVED` *and* the previous
  stage is effectively approved. Only effectively approved artifacts are used as inputs for
  generating the next artifact.
- **Gates are enforced in the service layer.** `generate`, `regenerate`, `edit` and `approve`
  call the workflow service first; a failed gate raises HTTP 409 with
  `{blocked, message, reason, required_stage, current_stage_status, suggested_action}`.
  Rejecting is always allowed. Class and sequence diagrams additionally require an approved
  domain model.
- **Invalidation.** Editing, regenerating or rejecting an artifact (or changing a feature)
  moves every approved artifact derived from it to `REQUIRES_REVIEW` and writes a version
  record explaining why. It returns to `APPROVED` only through validation and a human approval.

---

## Artifacts

All artifact types share one table and one lifecycle. The type-specific payload is JSON in
`artifacts.content`.

| Type | Content |
| --- | --- |
| `REQUIREMENTS` | `schema_version: 2` and a list of FR and NFR objects (see the README). |
| `SRS` | Narrative sections from the model plus sections rendered from the approved requirements. |
| `ARCHITECTURE` | Style and components (`CMP-###`) with responsibilities, dependencies and requirement links. |
| `DOMAIN_MODEL` | `model` (entities `ENT-###`, relationships `REL-###`, business rules `BR-###`) and the diagram rendered from it. |
| `UML_CLASS`, `UML_SEQUENCE` | A list of diagrams: id, title, PlantUML source and links to requirements, domain entities and components. |

**Identifiers.** Requirement ids are assigned by `requirement_ids.py`: an id is kept only if it
already belongs to the same requirement in the previous content; otherwise the next number that
was never used in *any* stored version is taken. Edits keep ids stable; removed ids are never
reused for a different requirement (validation reports `REQ_ID_REUSED`).
`normalize-ids` migrates legacy `REQ-###` ids everywhere they are referenced while keeping the
earlier versions.

**Domain model rendering.** The model is stored as structured data and the PlantUML source is
generated from it by code (`domain_model.py`), so the picture always matches the entities. If a
user edits only the source, the edit is kept and validation warns that it differs from the model.

---

## Validation

Validators in `artifacts/validation/` are deterministic and run on generation, edit and
approval. Each returns `PASSED`, `PASSED_WITH_WARNINGS` or `FAILED` with errors and warnings,
each carrying a code, message, path and suggestion. Approval is refused while errors exist.

| Artifact | Main checks |
| --- | --- |
| Requirements | Required fields, FR/NFR id format and type match, uniqueness, retired-id reuse, acceptance / measurable criteria, NFR categories, source features exist and are approved, feature coverage |
| SRS | Required sections, section ids, every requirement referenced |
| Architecture | Component ids and names, dependencies exist, requirement links, requirement coverage |
| Domain model | Entity/relationship/rule structure, cardinality syntax, inheritance cycles, isolated entities, requirement links and coverage, diagram syntax |
| UML | Structural PlantUML checker (envelope, braces, blocks, declared classes/participants) plus the real PlantUML syntax check when installed; references to requirements, domain entities and components |

The **AI critique** is stored separately (`ai_critique`), labelled advisory and never changes a
status.

---

## Traceability

`trace_links` is rebuilt from an artifact's content whenever that content changes:

| From | Relation | To |
| --- | --- | --- |
| Requirement | `DERIVED_FROM` | Feature |
| Component | `IMPLEMENTS` / `DEPENDS_ON` | Requirement / Component |
| Domain entity | `MODELS` | Requirement |
| UML diagram | `DESCRIBES` | Domain entity, component, requirement |

`GET /projects/{id}/dependencies` returns the links; `GET /projects/{id}/consistency` reports
dangling references (errors) and uncovered features, requirements, components and domain
entities (warnings).

---

## UML rendering

`artifacts/uml_render.py` runs the configured PlantUML command locally. PlantUML draws an
"error picture" and exits with status 0 on bad input, so a syntax check always runs first and a
failing source never produces an image. Sources are limited in size, may not use includes or
environment access, and run with PlantUML's most restrictive security profile and a timeout in an
empty temporary directory. Successful SVGs are cached by source hash. The frontend shows the SVG
as an `<img>`, so it cannot run scripts.

---

## Persistence schema (platform only)

PostgreSQL stores the platform's own records. It is not a schema for any target application.

```
projects ─┬─< features ─┬─< feature_versions
          │             └─< user_decisions
          ├─< artifacts ─┬─< artifact_versions
          │              ├─< artifact_decisions
          │              └─< trace_links (owner artifact)
          └─< artifact_decisions / trace_links (project)
```

| Table | Notes |
| --- | --- |
| `projects` | `status` (ACTIVE, ARCHIVED), `stage` (CREATED, EXTRACTION_DONE) |
| `features` | `status` (GENERATED, PENDING_REVIEW, APPROVED, REJECTED), `current_version` |
| `feature_versions` | Snapshot per change: CREATED, EDITED, STATUS_CHANGE |
| `user_decisions` | Approve / reject audit trail |
| `artifacts` | Unique per `(project_id, type)`; `status` (PENDING_REVIEW, APPROVED, REJECTED, REQUIRES_REVIEW), `content`, `source_refs`, `validation_result`, `ai_critique` (JSONB) |
| `artifact_versions` | Immutable content, status and validation snapshot per version, with change type and note |
| `artifact_decisions` | Approval / rejection history with version and reason |
| `trace_links` | Source and target kind/ref and relation |

Migrations (`backend/alembic/versions/`): `0001` creates the project and feature tables, `0002`
creates the artifact, version, decision and traceability tables.

---

## Key design decisions

- **Domain-driven modules.** Each lifecycle concern lives in one place; routes, schemas, logic
  and models follow the same convention.
- **Replaceable model.** The backend depends on an abstract `LLMProvider.generate(prompt)`; the
  concrete provider is chosen by `LLM_PROVIDER`.
- **Deterministic validation separate from AI critique.** Approval depends only on the
  deterministic result and a human decision.
- **Gates in the service layer.** The frontend explains a block, but the backend decides it.
- **Immutable versions.** Edits, regenerations and status changes append versions; nothing is
  overwritten, and rejection is a status change rather than a delete.
- **Backend-assigned identifiers.** The model proposes content; code assigns FR/NFR/ENT/REL/BR
  ids so they are consistent and stable.
- **Alembic-only schema changes.** Every environment is reproducible with `alembic upgrade head`.
- **Environment-driven configuration.** URLs, model names and the renderer command come from
  environment variables or `.env`; no secrets are committed.
