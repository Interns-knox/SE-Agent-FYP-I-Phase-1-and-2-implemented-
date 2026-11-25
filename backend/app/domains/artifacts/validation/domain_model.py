"""Deterministic validation of the DOMAIN_MODEL artifact."""

from typing import Any

from app.domains.artifacts.domain_model import (
    CARDINALITY,
    ENTITY_KINDS,
    IDENT,
    REL_KINDS,
    model_of,
    render_plantuml,
)

from .result import Report, ValidationContext, as_list, is_blank
from .uml import validate_plantuml


def _norm(s: str) -> str:
    return "".join(s.split())


def validate_domain_model(content: dict[str, Any], ctx: ValidationContext) -> Report:
    r = Report()
    r.check("structure")
    model = model_of(content)
    ents = as_list(model.get("entities"))
    if not ents:
        r.error("DM_EMPTY", "'model.entities' must be a non-empty list.", "model.entities",
                "Identify the business entities of the project.")
        return r
    if len(ents) < 3:
        r.warning("DM_TOO_SMALL", f"Only {len(ents)} entities; a project domain normally has "
                  "more distinct business concepts.", "model.entities")

    r.check("entities")
    ids: dict[str, int] = {}
    names: dict[str, str] = {}
    for i, e in enumerate(ents):
        p = f"model.entities[{i}]"
        if not isinstance(e, dict):
            r.error("DM_ENTITY_NOT_OBJECT", "Entity is not an object.", p)
            continue
        eid, name = e.get("id"), e.get("name")
        if is_blank(eid):
            r.error("DM_ENTITY_ID_MISSING", "Entity has no id.", f"{p}.id",
                    "Use ENT-001 style ids.")
        elif eid in ids:
            r.error("DM_ENTITY_ID_DUPLICATE", f"Entity id '{eid}' is duplicated.", f"{p}.id")
        else:
            ids[eid] = i
        if is_blank(name):
            r.error("DM_ENTITY_NAME_MISSING", f"{eid or p}: name is missing.", f"{p}.name")
            continue
        if not IDENT.match(name):
            r.error("DM_ENTITY_NAME_INVALID",
                    f"Entity name '{name}' must be a single PascalCase identifier.",
                    f"{p}.name", "Use letters and digits only, e.g. BookCopy.")
        key = name.casefold()
        if key in names:
            r.error("DM_ENTITY_NAME_DUPLICATE", f"Entity name '{name}' is duplicated.",
                    f"{p}.name")
        names[key] = name
        if e.get("kind") not in ENTITY_KINDS:
            r.error("DM_ENTITY_KIND_INVALID",
                    f"{name}: kind must be one of {sorted(ENTITY_KINDS)}.", f"{p}.kind")
        if is_blank(e.get("description")):
            r.error("DM_ENTITY_DESCRIPTION_MISSING", f"{name}: description is missing.",
                    f"{p}.description", "Describe the business meaning of the entity.")
        attrs = as_list(e.get("attributes"))
        if not attrs and e.get("kind") != "ACTOR":
            r.warning("DM_ENTITY_NO_ATTRIBUTES", f"{name}: no attributes defined.",
                      f"{p}.attributes")
        seen_attr: set[str] = set()
        for j, a in enumerate(attrs):
            an = a.get("name") if isinstance(a, dict) else None
            if is_blank(an):
                r.error("DM_ATTRIBUTE_NAME_MISSING", f"{name}: attribute {j} has no name.",
                        f"{p}.attributes[{j}].name")
            elif an in seen_attr:
                r.error("DM_ATTRIBUTE_DUPLICATE", f"{name}: attribute '{an}' is duplicated.",
                        f"{p}.attributes[{j}].name")
            else:
                seen_attr.add(an)
        reqs = as_list(e.get("requirement_ids"))
        if not reqs:
            r.warning("DM_ENTITY_UNTRACED", f"{name}: not linked to any requirement.",
                      f"{p}.requirement_ids")
        for rid in reqs:
            if ctx.requirements is not None and rid not in ctx.requirements:
                r.error("DM_REQUIREMENT_UNKNOWN", f"{name}: unknown requirement '{rid}'.",
                        f"{p}.requirement_ids")

    r.check("relationships")
    rels = as_list(model.get("relationships"))
    if not rels:
        r.error("DM_NO_RELATIONSHIPS", "The model defines no relationships.",
                "model.relationships", "Relate the entities (associations, composition, ...).")
    related: set[str] = set()
    rseen: set[str] = set()
    parents: dict[str, str] = {}
    for i, rel in enumerate(rels):
        p = f"model.relationships[{i}]"
        if not isinstance(rel, dict):
            r.error("DM_REL_NOT_OBJECT", "Relationship is not an object.", p)
            continue
        rid = rel.get("id")
        if is_blank(rid) or rid in rseen:
            r.error("DM_REL_ID_INVALID", f"Relationship {i}: id is missing or duplicated.",
                    f"{p}.id")
        else:
            rseen.add(rid)
        a, b = rel.get("from"), rel.get("to")
        ok = True
        for side, v in (("from", a), ("to", b)):
            if not isinstance(v, str) or v.casefold() not in names:
                r.error("DM_REL_ENTITY_UNKNOWN",
                        f"Relationship {rid or i}: '{side}' entity '{v}' does not exist.",
                        f"{p}.{side}", "Use an entity name from model.entities.")
                ok = False
        kind = rel.get("kind")
        if kind not in REL_KINDS:
            r.error("DM_REL_KIND_INVALID",
                    f"Relationship {rid or i}: kind must be one of {sorted(REL_KINDS)}.",
                    f"{p}.kind")
        if kind != "INHERITANCE":
            if is_blank(rel.get("label")):
                r.warning("DM_REL_LABEL_MISSING", f"Relationship {rid or i}: no label.",
                          f"{p}.label")
            for side in ("from_cardinality", "to_cardinality"):
                c = rel.get(side)
                if not isinstance(c, str) or not CARDINALITY.match(c):
                    r.error("DM_REL_CARDINALITY_INVALID",
                            f"Relationship {rid or i}: {side} '{c}' is not valid "
                            "(use 1, 0..1, *, 0..*, 1..*).", f"{p}.{side}")
        elif ok:
            if a == b:
                r.error("DM_INHERITANCE_SELF", f"{a} cannot inherit from itself.", p)
            parents[a] = b
        if ok:
            related.update((a.casefold(), b.casefold()))
    for child in parents:  # cycle check
        seen, cur = set(), child
        while cur in parents:
            if cur in seen:
                r.error("DM_INHERITANCE_CYCLE", f"Inheritance cycle involving {child}.",
                        "model.relationships")
                break
            seen.add(cur)
            cur = parents[cur]
    if len(ents) > 1:
        for key, name in names.items():
            if key not in related:
                r.warning("DM_ENTITY_ISOLATED", f"{name} has no relationships.",
                          "model.relationships")

    r.check("business_rules")
    for i, br in enumerate(as_list(model.get("business_rules"))):
        p = f"model.business_rules[{i}]"
        if not isinstance(br, dict) or is_blank(br.get("description")):
            r.error("DM_RULE_DESCRIPTION_MISSING", f"Business rule {i} has no description.", p)
            continue
        for en in as_list(br.get("entities")):
            if not isinstance(en, str) or en.casefold() not in names:
                r.error("DM_RULE_ENTITY_UNKNOWN",
                        f"Business rule {br.get('id') or i} refers to unknown entity '{en}'.", p)
        for rid in as_list(br.get("requirement_ids")):
            if ctx.requirements is not None and rid not in ctx.requirements:
                r.error("DM_REQUIREMENT_UNKNOWN",
                        f"Business rule {br.get('id') or i}: unknown requirement '{rid}'.", p)
    if not as_list(model.get("business_rules")):
        r.warning("DM_NO_BUSINESS_RULES", "No business rules or constraints documented.",
                  "model.business_rules")

    r.check("requirement_coverage")
    if ctx.requirements is not None:
        linked = {x for e in ents if isinstance(e, dict) for x in as_list(e.get("requirement_ids"))}
        linked |= {x for b in as_list(model.get("business_rules")) if isinstance(b, dict)
                   for x in as_list(b.get("requirement_ids"))}
        for rid, req in ctx.requirements.items():
            if req.get("type") == "FUNCTIONAL" and rid not in linked:
                r.warning("REQ_NOT_IN_DOMAIN_MODEL",
                          f"Functional requirement {rid} is not reflected in the domain model.",
                          "model.entities", "Link the entity or rule that realizes it.")

    r.check("plantuml_syntax")
    diagrams = as_list(content.get("diagrams"))
    if not diagrams:
        r.error("DM_DIAGRAM_MISSING", "The domain model has no diagram.", "diagrams")
    expected = _norm(render_plantuml(model))
    for i, d in enumerate(diagrams):
        p = f"diagrams[{i}]"
        if not isinstance(d, dict):
            r.error("UML_DIAGRAM_NOT_OBJECT", "Diagram entry is not an object.", p)
            continue
        validate_plantuml(d.get("plantuml"), "class", f"{p}.plantuml", r)
        if isinstance(d.get("plantuml"), str) and _norm(d["plantuml"]) != expected:
            r.warning("DM_DIAGRAM_CUSTOMIZED",
                      "The diagram source differs from the diagram rendered from the "
                      "structured model; the picture may not match the entities.", p,
                      "Edit the model, or accept the customized source.")
    return r
