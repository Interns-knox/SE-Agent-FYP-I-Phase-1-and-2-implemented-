# SE Agent — AI-Assisted Requirements and Design Engineering

SE Agent is a web platform that applies a locally hosted large language model (Ollama +
Qwen3:8B) to the early software-engineering lifecycle while keeping a human engineer in control
of every decision. A user describes a project in natural language; the platform extracts
candidate features, then generates requirements, a Software Requirements Specification (SRS),
a system architecture, a conceptual domain model and UML diagrams. Every AI output is a
**candidate**: it is validated by deterministic backend checks, then edited, approved or rejected
by a person, and every change is versioned.

**Final Year Project** — BS Software Engineering, FAST NUCES Islamabad (Fall 2026).
**Team:** Muhammad Yasim Malik, Muhammad Ahmad, Muhammad Mahyar Zeb.
**Supervisor:** Mr. Irfan Ullah.
**UN SDG alignment:** SDG 9 — Industry, Innovation, and Infrastructure.

> **This repository is the FYP-I submission.** It contains Phase 1 and Phase 2 only. Later
> lifecycle stages are not part of this repository.

---

## Contents

1. [FYP-I scope](#1-fyp-i-scope)
2. [Features](#2-features)
3. [How the workflow works](#3-how-the-workflow-works)
4. [Architecture and technology stack](#4-architecture-and-technology-stack)
5. [Persistence: what the database is for](#5-persistence-what-the-database-is-for)
6. [Installation](#6-installation)
7. [Configuration](#7-configuration)
8. [Database setup and migrations](#8-database-setup-and-migrations)
9. [Running the application](#9-running-the-application)
10. [Demonstration walkthrough](#10-demonstration-walkthrough)
11. [Testing and quality checks](#11-testing-and-quality-checks)
12. [API summary](#12-api-summary)
13. [Project structure](#13-project-structure)
14. [Known limitations](#14-known-limitations)

---

## 1. FYP-I scope

| Phase | Deliverable | Status in this repository |
| --- | --- | --- |
| **Phase 1** | Platform architecture | Implemented (see [docs/architecture.md](docs/architecture.md)) |
| | Workspace management | Implemented |
| | Context management | Implemented |
| | Feature extraction | Implemented |
| | Human editing and approval of features | Implemented |
| **Phase 2** | Requirements generation (FR and NFR) | Implemented |
| | Human validation | Implemented (deterministic validation, edit, approve, reject) |
| | Domain modeling | Implemented |
| | PlantUML generation and visual rendering | Implemented |
| | Traceability | Implemented |

The exact in-scope and out-of-scope lists are in [docs/scope.md](docs/scope.md).

---

## 2. Features

### Phase 1 — platform, workspace, context, feature extraction

- **Workspace management.** Create, list and open projects. Each project has its own workspace
  page showing its description, stage, feature review and context.
- **Context management.** A structured project context (project details, approved features,
  all-feature summary, last extraction time) assembled on demand from the stored records.
- **Feature extraction.** The local model proposes 3 to 10 candidate features from the project
  description. Output is parsed defensively (code fences, reasoning blocks, retries) and
  de-duplicated.
- **Human review.** Every feature can be edited, approved, rejected and restored. Each change
  creates a version record and every decision is stored in an audit trail.

### Phase 2 — requirements, validation, domain model, PlantUML, traceability

- **Requirements generation.** Functional requirements get `FR-###` identifiers and
  non-functional requirements get `NFR-###` identifiers. Identifiers are assigned by the
  backend (never trusted from the model), are unique, stay stable across edits and
  regeneration, and are never reused after a requirement is removed.
  - Functional requirements record: title, description, actor, preconditions, expected behavior,
    acceptance criteria, priority and source feature.
  - Non-functional requirements record: category (performance, security, reliability,
    availability, usability, maintainability, scalability), description, measurable criterion,
    priority and source. When the project context gives no target value, the model must flag
    the requirement as *needs clarification* instead of inventing a number.
- **SRS and system architecture.** The SRS combines model-written narrative sections with
  sections rendered from the approved requirements. The architecture lists components, their
  responsibilities, dependencies and the requirements each one implements.
- **Domain modeling.** A conceptual domain model of the actual project: entities, attributes,
  relationships with cardinalities (one-to-one, one-to-many, many-to-many), business rules and
  links to requirements. It is stored as structured data and its diagram is rendered from that
  data by code.
- **UML.** Domain model, class diagram and sequence diagrams, written in PlantUML.
- **Visual rendering.** Diagrams are shown as images by default, rendered locally by PlantUML
  (no external service). The viewer supports pan, zoom, fit-to-screen, reset, full screen, a
  separate PlantUML source view and source editing with a live preview that keeps the last
  valid image while you type.
- **Deterministic validation.** Backend checks, not model self-assessment: required fields,
  identifier format and uniqueness, missing descriptions and acceptance criteria, unknown or
  duplicate references, UML syntax (structural checker plus the real PlantUML checker), domain
  model consistency and missing links between artifacts. Results contain errors, warnings and
  an actionable suggestion for each. An optional AI critique is shown separately and is
  advisory only.
- **Human approval and history.** Every artifact can be edited, validated, approved, rejected
  and regenerated. Each change creates a new version with its validation result; approvals and
  rejections are recorded; any two versions can be compared as a diff.
- **Traceability.** Links are derived from artifact content: requirement → feature, component →
  requirement, domain entity → requirement and UML diagram → domain entity / component /
  requirement. A consistency check reports dangling references and uncovered requirements,
  components and entities.

---

## 3. How the workflow works

The application guides the user through five stages. A stage is locked until the previous one
is approved.

```
1 Project Features → 2 Requirements → 3 SRS → 4 Architecture → 5 UML Diagrams
                                                               (domain model, class
                                                                diagram, sequence diagrams)
```

| Stage | Requires before it can be generated, edited or approved |
| --- | --- |
| Requirements | At least one approved feature and no feature pending review |
| SRS | Requirements approved |
| Architecture | SRS approved |
| UML Diagrams | Architecture approved (class and sequence diagrams also need the approved domain model) |

- **Enforced by the backend.** Generate, regenerate, edit and approve return HTTP 409 with a
  structured body (`blocked`, `reason`, `required_stage`, `current_stage_status`,
  `suggested_action`) when a prerequisite is not met, so the API cannot be used to skip a stage.
  The UI shows the same information as a blocking message with a button back to the stage that
  must be completed.
- **Stage statuses:** `NOT_STARTED`, `IN_PROGRESS`, `PENDING_REVIEW`, `APPROVED`, `BLOCKED`,
  `REQUIRES_REVIEW`.
- **Stale approvals are never silently valid.** Editing, regenerating or rejecting an artifact,
  or changing a feature, moves every approved artifact derived from it to `REQUIRES_REVIEW`
  (with a history entry). Such artifacts cannot be used as inputs until they are validated and
  approved again.
- **Nothing is auto-approved.** Generated artifacts always start as `PENDING_REVIEW`. The
  "Approve … and Continue" button approves the artifacts shown on screen after the server
  validates them again, and navigates only after the server confirms the approval.

---

## 4. Architecture and technology stack

```
Browser ──► React + TypeScript SPA (Vite)  ──HTTP/JSON──►  FastAPI backend ──► PostgreSQL
                                                               │
                                                               ├──► Ollama (Qwen3:8B)   AI proposals
                                                               └──► PlantUML (local)    validation + SVG
```

| Layer | Technology (as used in this repository) |
| --- | --- |
| Frontend | React 19, TypeScript 6, Vite 8, React Router 6, Axios; ESLint |
| Backend | Python 3.12+, FastAPI, Pydantic v2 / pydantic-settings, SQLAlchemy 2, Alembic, httpx |
| Persistence | PostgreSQL (psycopg2) |
| AI | Ollama serving `qwen3:8b`, behind an `LLMProvider` abstraction |
| Diagrams | PlantUML (needs Java and Graphviz), rendered to SVG locally |
| Testing | pytest, FastAPI TestClient, Ruff; headless Chrome (puppeteer-core) for browser verification |

The backend is organized by domain under `backend/app/domains/` (workspace, features, context,
ai, artifacts, workflow); each domain has `router.py`, `schemas.py`, `service.py` and, where it
owns data, `models.py`. Details and design decisions: [docs/architecture.md](docs/architecture.md).

---

## 5. Persistence: what the database is for

PostgreSQL is used **only as the platform's own persistence**. It stores the records SE Agent
needs to work: workspaces, extracted features and their versions, user decisions, generated
artifacts and their versions, validation results, approval history and traceability links.

This submission does **not** include a database-design deliverable, and it does not generate or
implement a database for any target application. There is no database-design artifact, page or
endpoint.

Platform tables (created by the Alembic migrations):

| Table | Purpose |
| --- | --- |
| `projects` | Workspaces / projects and their stage |
| `features`, `feature_versions`, `user_decisions` | Extracted features, their version history and review decisions |
| `artifacts` | One row per artifact type per project: content, status, version, source references, validation result |
| `artifact_versions` | Immutable snapshot of every artifact version, with its validation result |
| `artifact_decisions` | Approval and rejection history |
| `trace_links` | Traceability links derived from artifact content |

---

## 6. Installation

### Prerequisites

| Requirement | Version | Notes |
| --- | --- | --- |
| Python | 3.12 or newer | |
| Node.js | 20.19+ or 22.12+ | Vite 8 requires it. Older Node versions cannot install the native build bindings. |
| PostgreSQL | 14 or newer (verified with 16) | A database you can create |
| Ollama | current | `ollama pull qwen3:8b` |
| PlantUML + Graphviz | current | Needed to render diagram images (see below) |

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Frontend

```bash
cd frontend
npm ci
```

### PlantUML (local diagram rendering)

PlantUML needs Java and Graphviz. Any installation that provides a `plantuml` command works,
for example with conda-forge:

```bash
micromamba create -n uml -c conda-forge plantuml graphviz
ln -s "$(micromamba run -n uml which plantuml)" ~/.local/bin/plantuml   # or set PLANTUML_COMMAND
```

On Debian or Ubuntu: `sudo apt install plantuml graphviz`. Check it with
`GET /uml/renderer`. If PlantUML is missing the application still works, but diagrams show a
"renderer unavailable" message and UML syntax is only checked by the built-in structural checker.

---

## 7. Configuration

Copy the template and edit it. **Never commit `.env`**; it is git-ignored.

```bash
cp .env.example .env
```

The backend reads `.env` from the repository root or from `backend/`.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgresql+psycopg2://se_agent:<password>@localhost:5432/se_agent` |
| `OLLAMA_URL`, `OLLAMA_MODEL`, `LLM_PROVIDER` | Local model endpoint (`http://localhost:11434`, `qwen3:8b`, `ollama`) |
| `LLM_TIMEOUT_SECONDS` | Seconds to wait for one model call. Use `600`; a domain model can take 4-5 minutes on a modest GPU. |
| `OLLAMA_NUM_CTX`, `OLLAMA_THINK` | Optional. `8192` and `false` make Qwen3 much faster on modest GPUs. |
| `PLANTUML_COMMAND` | PlantUML executable (default `plantuml`) |
| `CORS_ORIGINS` | Browser origins allowed to call the API (default `http://localhost:5173`) |
| `VITE_API_URL` | API URL used by the frontend (default `http://localhost:8000`); set it in `frontend/.env.local` |

---

## 8. Database setup and migrations

Create a PostgreSQL role and database (adjust names and choose your own password):

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE se_agent WITH LOGIN PASSWORD '<choose-a-password>';
CREATE DATABASE se_agent OWNER se_agent;
SQL
```

Put the same credentials in `DATABASE_URL`, then apply the migrations:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head      # creates the platform tables (revisions 0001, 0002)
alembic current           # should print: 0002 (head)
alembic check             # confirms the models and migrations match
```

Alembic is the only mechanism that creates or changes the schema.

---

## 9. Running the application

Start Ollama first (`ollama serve`; the model must be pulled).

```bash
# terminal 1 — backend, http://localhost:8000  (API docs at /docs)
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload

# terminal 2 — frontend, http://localhost:5173
cd frontend
npm run dev
```

---

## 10. Demonstration walkthrough

1. Open `http://localhost:5173`, choose **New project**, and enter a name and a description of the
   system (for example a library management system).
2. In the project workspace, **Extract Features**. Review the candidates: edit, approve or reject
   each one. The summary shows total, approved, pending and rejected counts.
3. When no feature is pending and at least one is approved, **Move to Requirements** becomes
   available. (Opening the requirements URL earlier shows "Feature approval required".)
4. **Generate** requirements. Inspect the FR and NFR tables and the validation result, edit if
   needed, then **Approve Requirements and Continue to SRS**.
5. Generate and approve the **SRS**, then the **Architecture**.
6. On **UML Diagrams**, generate and approve the **Domain Model** first, then the **Class Diagram**
   and **Sequence Diagrams**. Each is shown as an image; use the toolbar to zoom, fit, view the
   PlantUML source or edit it.
7. Read the **Dependency model** panel at the bottom of each design page for the traceability
   links and run **Check cross-artifact consistency**.
8. Use **Version history** on any artifact to see versions, validation snapshots, decisions and
   a diff against the previous version.
9. Edit an upstream artifact (for example the SRS) and return to the workspace: the artifacts
   derived from it now show `REQUIRES_REVIEW` until they are approved again.

---

## 11. Testing and quality checks

### Backend

```bash
cd backend && source .venv/bin/activate
pytest tests/unit tests/api         # no external services needed
ruff check app tests
pytest -m integration               # needs live Ollama and PostgreSQL
```

The unit and API tests run the real routers, services, validators and ORM models on in-memory
SQLite and replace only the language model with a scripted test double. Four tests that
exercise the real PlantUML renderer are skipped automatically when PlantUML is not installed.

### Frontend

```bash
cd frontend
npx tsc -b            # type-check
npx eslint src scripts
npm run build         # production build
```

### Browser verification of the whole workflow

A headless-Chrome script walks the complete journey (features → requirements → SRS →
architecture → domain model → class and sequence diagrams → traceability) against a throw-away
backend that uses a scripted model and the real renderer:

```bash
# terminal 1
cd backend && PLANTUML_COMMAND=plantuml CORS_ORIGINS=http://localhost:5174 \
  python -m tests.e2e.server 8001
# terminal 2
cd frontend && VITE_API_URL=http://localhost:8001 npx vite --port 5174
# terminal 3 (needs Google Chrome; set CHROME_PATH if it is not /usr/bin/google-chrome)
cd frontend && API_URL=http://localhost:8001 UI_URL=http://localhost:5174 npm run verify:ui
```

---

## 12. API summary

Interactive documentation is served at `http://localhost:8000/docs`.

| Area | Endpoints |
| --- | --- |
| Health | `GET /health` |
| Workspaces | `POST /projects`, `GET /projects`, `GET /projects/{id}`, `GET /projects/{id}/context` |
| Features | `POST /projects/{id}/extract`, `GET /projects/{id}/features`, `PATCH /features/{id}`, `POST /features/{id}/approve`, `/reject`, `/restore`, `GET /features/{id}/versions` |
| Workflow | `GET /projects/{id}/workflow` |
| Artifacts | `POST /projects/{id}/artifacts/generate`, `GET /projects/{id}/artifacts`, `GET`/`PUT /artifacts/{id}`, `POST /artifacts/{id}/regenerate`, `/validate`, `/approve`, `/reject`, `/critique` |
| History | `GET /artifacts/{id}/versions[/{n}]`, `/decisions`, `/diff` |
| Requirement ids | `POST /projects/{id}/artifacts/requirements/normalize-ids` (migrates legacy `REQ-###` ids) |
| Traceability | `GET /projects/{id}/dependencies`, `GET /projects/{id}/consistency` |
| Diagrams | `GET /uml/renderer`, `POST /uml/render` |

---

## 13. Project structure

```
.
├── README.md
├── .env.example                 # configuration template (copy to .env)
├── docs/
│   ├── architecture.md          # components, data flow, schema, design decisions
│   └── scope.md                 # FYP-I scope: in scope / out of scope
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                 # migrations 0001 (workspace, features), 0002 (artifacts, traceability)
│   ├── app/
│   │   ├── main.py  config.py  database.py
│   │   └── domains/
│   │       ├── workspace/       # projects and extraction entry point
│   │       ├── features/        # feature lifecycle, versions, decisions
│   │       ├── context/         # structured project context
│   │       ├── ai/              # LLMProvider, Ollama, feature extraction
│   │       ├── artifacts/       # requirements, SRS, architecture, domain model, UML,
│   │       │                    # validation, versions, traceability, PlantUML rendering
│   │       └── workflow/        # stages, approval gates, stale-approval handling
│   └── tests/                   # unit, api, integration, e2e harness
└── frontend/
    ├── scripts/verify-ui.mjs    # headless-Chrome workflow verification
    └── src/
        ├── api/  hooks/  types/
        ├── components/          # common, workspace, workflow, artifacts (incl. diagram viewer)
        └── pages/               # dashboard, create project, workspace, requirements, SRS,
                                 # architecture, UML
```

---

## 14. Known limitations

- **Model quality varies.** A locally hosted 8B model sometimes returns malformed JSON or
  weak content. The backend retries once, validates everything deterministically and reports
  errors, but a person must still review each artifact. Generating requirements or diagrams can
  take from under a minute to several minutes depending on the hardware.
- **Validation is structural.** It checks format, references and consistency. It cannot judge
  whether a requirement is *correct* for the real-world problem.
- **PlantUML is an external dependency** (Java and Graphviz). Without it, diagrams are not
  rendered and UML syntax is only checked structurally.
- **Single user, no authentication.** The platform is a local tool; it has no accounts or access
  control.
- **One artifact per type per project.** Regeneration creates a new version of the same
  artifact; there are no parallel alternative drafts.
