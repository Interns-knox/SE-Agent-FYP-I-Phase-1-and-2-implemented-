"""LLM prompt construction and response parsing for Phase 2 artifacts.

All generation goes through the existing ``LLMProvider`` abstraction. The parser
reuses the tolerant JSON extraction from Phase 1 (handles <think> blocks, code
fences, surrounding prose).
"""

import json
from typing import Any

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import settings
from app.domains.ai.extraction import _extract_json_object
from app.domains.ai.provider import LLMProvider
from app.domains.artifacts.models import ArtifactType

_COMMON = (
    "You are a senior software engineer. Return ONLY one valid JSON object, with no markdown, "
    "comments or explanation. Use exactly the field names shown. Do not invent ids that are not "
    "given to you for references; reuse the ids provided."
)

SCHEMAS: dict[ArtifactType, str] = {
    ArtifactType.REQUIREMENTS: (
        "Derive structured requirements from the approved features. JSON format:\n"
        '{"requirements":[\n'
        ' {"type":"FUNCTIONAL","title":"...","description":"The system shall ...",'
        '"actor":"who performs or triggers it","preconditions":["..."],'
        '"expected_behavior":"observable result","priority":"MUST",'
        '"acceptance_criteria":["testable criterion"],"source_feature_ids":["<feature uuid>"]},\n'
        ' {"type":"NON_FUNCTIONAL","category":"PERFORMANCE","description":"The system shall ...",'
        '"measurable_criterion":"target with a number and unit","priority":"SHOULD",'
        '"source_feature_ids":["<feature uuid>"],"needs_clarification":false}]}\n'
        "Rules: do NOT write ids; the system assigns FR-### and NFR-### itself (when revising, "
        "copy the \"id\" of requirements you keep). FUNCTIONAL requirements need actor, "
        "expected_behavior, at least one acceptance criterion and at least one "
        "source_feature_id taken from the feature list; cover every feature. NON_FUNCTIONAL "
        "category is one of PERFORMANCE, SECURITY, RELIABILITY, AVAILABILITY, USABILITY, "
        "MAINTAINABILITY, SCALABILITY. Give 3 or more non-functional requirements. NEVER invent "
        "numeric targets that the project description does not support: when the context gives "
        "no target, set \"needs_clarification\":true, add a \"clarification_note\" and write the "
        "criterion as 'TBD: <what must be decided>'. priority is MUST, SHOULD, COULD or WONT."
    ),
    ArtifactType.SRS: (
        "Write the narrative sections of a Software Requirements Specification. JSON format:\n"
        '{"sections":[{"id":"purpose","title":"Purpose","body":"..."},'
        '{"id":"scope","title":"Scope","body":"..."},'
        '{"id":"overall_description","title":"Overall Description","body":"..."},'
        '{"id":"assumptions_constraints","title":"Assumptions and Constraints","body":"..."}]}\n'
        "Use exactly those four section ids. Do not list the requirements; they are appended "
        "automatically."
    ),
    ArtifactType.ARCHITECTURE: (
        "Design a system architecture from the approved requirements and SRS. JSON format:\n"
        '{"style":"e.g. layered client-server","components":[{"id":"CMP-001","name":"...",'
        '"type":"e.g. frontend|api|service|database|external","responsibility":"...",'
        '"technology":"...","depends_on":["CMP-002"],"requirement_ids":["FR-001"]}]}\n'
        "Rules: ids are CMP-001..; every requirement must be allocated to at least one component "
        "via requirement_ids (use the exact FR-/NFR- ids given); depends_on only uses ids of "
        "components you define; every component has a clear single responsibility. Use 4 to 10 "
        "components."
    ),
    ArtifactType.DOMAIN_MODEL: (
        "Create the conceptual DOMAIN MODEL of this project: the real business concepts found in "
        "the approved requirements and architecture, independent of database tables or code. "
        "Be concise. JSON format:\n"
        '{"model":{"entities":[{"name":"PascalCaseName","kind":"ENTITY","description":"one short '
        'sentence","attributes":[{"name":"camelCase","type":"String"}],'
        '"requirement_ids":["FR-001"]}],'
        '"relationships":[{"from":"EntityA","to":"EntityB","label":"verb",'
        '"from_cardinality":"1","to_cardinality":"0..*","kind":"ASSOCIATION"}],'
        '"business_rules":[{"description":"one short sentence","entities":["EntityA"],'
        '"requirement_ids":["FR-001"]}]}}\n'
        "Rules: do not write ids. Discover the important entities of THIS project (not a generic "
        "example), at most 12; distinguish a concept from its individual instances when the "
        "requirements support it (e.g. a catalogue item vs. a physical copy). Give each entity "
        "3 to 6 key attributes (name and type only) and a description of at most 15 words. "
        "kind is ENTITY, VALUE_OBJECT, ACTOR or ENUMERATION. Relationship kind is ASSOCIATION, "
        "AGGREGATION, COMPOSITION or INHERITANCE (for INHERITANCE omit label and cardinalities; "
        "'from' is the child). Cardinalities are 1, 0..1, *, 0..*, 1..* (or n..m). Every entity "
        "must take part in a relationship. Entity names are single identifiers without spaces. "
        "List 3 to 8 business rules. Link entities and rules to requirement ids that exist."
    ),
    ArtifactType.UML_CLASS: (
        "Produce 1 to 3 detailed UML CLASS diagrams in PlantUML syntax, based on the approved "
        "architecture and domain model (include every domain entity; add technical classes such "
        "as services or repositories only where the architecture justifies them). JSON format:\n"
        '{"diagrams":[{"id":"CLS-001","title":"...","plantuml":'
        '"@startuml\\nclass Member {\\n  -email : String\\n  +register() : void\\n}\\n'
        'class Loan\\nMember \\"1\\" --> \\"0..*\\" Loan : makes\\n@enduml",'
        '"requirement_ids":["FR-001"],"domain_entity_ids":["ENT-001"],'
        '"component_ids":["CMP-001"]}]}\n'
        "Rules: each plantuml string begins with @startuml and ends with @enduml, declares every "
        "class it uses, shows attributes, important methods, multiplicity and inheritance or "
        "interfaces where justified, and never leaves a class without a relationship. Reference "
        "only the given requirement, domain entity (ENT-###) and component ids. Escape newlines "
        "as \\n and quotes as \\\" inside JSON strings."
    ),
    ArtifactType.UML_SEQUENCE: (
        "Produce 2 to 5 UML SEQUENCE diagrams in PlantUML syntax for the most important workflows "
        "found in the approved requirements (derive them from this project; do not use generic "
        "examples). JSON format:\n"
        '{"diagrams":[{"id":"SEQ-001","title":"workflow name","plantuml":"@startuml\\n'
        'actor User\\nparticipant API\\ndatabase DB\\nUser -> API : request\\nalt valid\\n'
        'API -> DB : query\\nelse invalid\\nAPI --> User : error\\nend\\n@enduml",'
        '"requirement_ids":["FR-001"],"domain_entity_ids":["ENT-001"],'
        '"component_ids":["CMP-001"]}]}\n'
        "Rules: each plantuml string begins with @startuml and ends with @enduml, declares every "
        "actor and participant (use architecture components as participants), shows requests, "
        "responses and relevant alternative or error paths, closes every alt/opt/loop with end. "
        "Reference only the given requirement, domain entity and component ids. Escape newlines "
        "as \\n inside JSON strings."
    ),
}

TITLES = {
    ArtifactType.REQUIREMENTS: "Requirements Specification",
    ArtifactType.SRS: "Software Requirements Specification",
    ArtifactType.ARCHITECTURE: "System Architecture",
    ArtifactType.UML_CLASS: "UML Class Diagrams",
    ArtifactType.UML_SEQUENCE: "UML Sequence Diagrams",
    ArtifactType.DOMAIN_MODEL: "Domain Model",
}


class PromptTooLarge(ValueError):
    """The prompt would not fit the configured model context window."""


def _compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _cut(text: Any, n: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _rel_view(r: dict) -> dict[str, Any]:
    card = None
    if r.get("kind") != "INHERITANCE":
        card = f"{r.get('from_cardinality')} to {r.get('to_cardinality')}"
    return {"from": r.get("from"), "to": r.get("to"), "kind": r.get("kind"),
            "label": r.get("label"), "cardinality": card}


def condense(label: str, content: Any) -> Any:
    """Short view of an approved artifact for use as context in a later stage.

    Later stages need identifiers, names and one-line meanings, not every acceptance
    criterion or diagram source. A condensed view keeps prompts inside the model's context
    window; without it the start of the prompt (the instructions) is silently cut off."""
    if not isinstance(content, dict):
        return content
    if label == "requirements":
        return [{"id": r.get("id"), "type": r.get("type"),
                 "title": _cut(r.get("title") or r.get("category"), 60),
                 "description": _cut(r.get("description"), 170)}
                for r in content.get("requirements", []) if isinstance(r, dict)]
    if label == "architecture":
        return {"style": content.get("style"),
                "components": [{"id": c.get("id"), "name": c.get("name"), "type": c.get("type"),
                                "responsibility": _cut(c.get("responsibility"), 140),
                                "depends_on": c.get("depends_on")}
                               for c in content.get("components", []) if isinstance(c, dict)]}
    if label == "SRS narrative":
        return [{"id": x.get("id"), "title": x.get("title"), "body": _cut(x.get("body"), 400)}
                for x in content.get("sections", []) if isinstance(x, dict)]
    if label == "domain model":
        m = content.get("model") if isinstance(content.get("model"), dict) else {}
        return {
            "entities": [{"id": e.get("id"), "name": e.get("name"), "kind": e.get("kind"),
                          "attributes": [f"{a.get('name')}:{a.get('type')}"
                                         for a in e.get("attributes", []) if isinstance(a, dict)]}
                         for e in m.get("entities", []) if isinstance(e, dict)],
            "relationships": [_rel_view(r) for r in m.get("relationships", [])
                              if isinstance(r, dict)],
            "business_rules": [{"description": _cut(b.get("description"), 140),
                                "entities": b.get("entities")}
                               for b in m.get("business_rules", []) if isinstance(b, dict)],
        }
    return content


def max_prompt_chars() -> int | None:
    """Characters of prompt that fit the configured context window (None = unknown)."""
    if not settings.OLLAMA_NUM_CTX:
        return None
    # about 2.5 characters per token for dense JSON, leaving a third of the window for the reply
    return int(settings.OLLAMA_NUM_CTX * 2 / 3 * 2.5)


def build_prompt(
    artifact_type: ArtifactType,
    project: dict[str, str],
    features: list[dict[str, str]],
    upstream: dict[str, Any],
    feedback: str | None,
    previous_content: dict | None = None,
) -> str:
    if artifact_type == ArtifactType.REQUIREMENTS:
        feats: Any = features  # requirements cite feature ids and need the full descriptions
    else:
        feats = [{"id": f["id"], "name": f["name"]} for f in features]
    parts = [
        _COMMON,
        SCHEMAS[artifact_type],
        f"Project name: {project['name']}\nProject description: {project['description']}",
        "Approved features (JSON):\n" + _compact(feats),
    ]
    for label, content in upstream.items():
        parts.append(f"Approved {label} (JSON):\n" + _compact(condense(label, content)))
    if previous_content is not None and feedback:
        parts.append("Previous draft (JSON):\n" + _compact(previous_content))
    if feedback:
        parts.append(f"Reviewer feedback to address:\n{feedback}")
    # The instructions come first; repeat the task last so it survives any truncation.
    parts.append(f"Now answer with ONLY the single JSON object for the {artifact_type.value} "
                 "artifact in the format given at the top. No explanation, no markdown.")
    prompt = "\n\n".join(parts)
    limit = max_prompt_chars()
    if limit is not None and len(prompt) > limit:
        raise PromptTooLarge(
            f"The prompt for {artifact_type.value} is {len(prompt)} characters, more than the "
            f"{limit} that fit the configured context window (OLLAMA_NUM_CTX="
            f"{settings.OLLAMA_NUM_CTX}). Increase OLLAMA_NUM_CTX or shorten the project "
            "description, then try again.")
    return prompt


def call_llm_json(provider: LLMProvider, prompt: str) -> dict[str, Any]:
    """Call the provider and return a parsed JSON object (one retry on bad output)."""
    try:
        try:
            return _parse(provider.generate(prompt))
        except (ValidationError, json.JSONDecodeError, ValueError):
            return _parse(provider.generate(prompt))
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="The AI model did not return valid JSON for this artifact."
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="AI service request timed out.") from exc
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=503, detail="AI service is unavailable.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=503, detail="AI service rejected the request (model may be unavailable)."
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="AI service communication error.") from exc


def _parse(raw: str) -> dict[str, Any]:
    data = json.loads(_extract_json_object(raw))
    if not isinstance(data, dict):
        raise ValueError("model response is not a JSON object")
    return data


def build_critique_prompt(artifact_type: ArtifactType, content: dict[str, Any]) -> str:
    return (
        "You are a reviewing software architect. Critique the following "
        f"{artifact_type.value} artifact for gaps, ambiguity and inconsistencies. Reply with "
        "plain text: at most 8 short bullet points, most important first.\n\n"
        + json.dumps(content, indent=1)
    )


def render_requirement_sections(requirements: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Deterministically render the requirement sections of the SRS from stored data."""

    def render(kind: str) -> str:
        lines: list[str] = []
        for r in requirements:
            if r.get("type") != kind:
                continue
            head = r.get("title") or str(r.get("category", "")).title()
            lines.append(f"**{r.get('id')} {head}** ({r.get('priority', '')})")
            lines.append(str(r.get("description", "")))
            if r.get("actor"):
                lines.append(f"- Actor: {r['actor']}")
            for pre in r.get("preconditions") or []:
                lines.append(f"- Precondition: {pre}")
            if r.get("expected_behavior"):
                lines.append(f"- Expected behavior: {r['expected_behavior']}")
            if r.get("measurable_criterion"):
                lines.append(f"- Measurable criterion: {r['measurable_criterion']}")
            for ac in r.get("acceptance_criteria") or []:
                lines.append(f"- Acceptance: {ac}")
            lines.append("")
        return "\n".join(lines).strip() or "None."

    return [
        {"id": "functional_requirements", "title": "Functional Requirements",
         "body": render("FUNCTIONAL")},
        {"id": "non_functional_requirements", "title": "Non-Functional Requirements",
         "body": render("NON_FUNCTIONAL")},
    ]
