"""Domain model content: normalization and deterministic PlantUML rendering.

The model is stored as structured data (entities, relationships, business rules). The visual
diagram is rendered from that data by code, so the picture always matches the entities and a
language-model slip cannot produce a diagram with invalid syntax.
"""

import re
from typing import Any

ENTITY_KINDS = {"ENTITY", "VALUE_OBJECT", "ACTOR", "ENUMERATION"}
REL_KINDS = {"ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE"}
CARDINALITY = re.compile(r"^(\d+|\*)(\.\.(\d+|\*))?$")
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
DIAGRAM_ID = "DM-001"


def _list(v: Any) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def model_of(content: Any) -> dict[str, Any]:
    m = content.get("model") if isinstance(content, dict) else None
    return m if isinstance(m, dict) else {}


def _stereotype(kind: str) -> str:
    return {"VALUE_OBJECT": "value object", "ACTOR": "actor", "ENUMERATION": "enumeration"
            }.get(kind, "entity")


def render_plantuml(model: dict[str, Any], title: str = "Domain Model") -> str:
    """PlantUML class-diagram source for a structured domain model."""
    ents = _list(model.get("entities"))
    names = {e.get("name") for e in ents}
    out = ["@startuml", f"title {title}", "hide empty methods",
           "skinparam classAttributeIconSize 0", "left to right direction"]
    for e in ents:
        name = e.get("name")
        if not isinstance(name, str) or not IDENT.match(name):
            continue
        st = _stereotype(str(e.get("kind", "ENTITY")))
        attrs = [a for a in _list(e.get("attributes")) if isinstance(a.get("name"), str)]
        if attrs:
            out.append(f"class {name} <<{st}>> {{")
            for a in attrs:
                typ = str(a.get("type") or "").strip()
                out.append(f"  {a['name']}" + (f" : {typ}" if typ else ""))
            out.append("}")
        else:
            out.append(f"class {name} <<{st}>>")
    for r in _list(model.get("relationships")):
        a, b = r.get("from"), r.get("to")
        if a not in names or b not in names:
            continue
        kind = r.get("kind", "ASSOCIATION")
        label = str(r.get("label") or "").replace("\n", " ").strip()
        suffix = f" : {label}" if label else ""
        if kind == "INHERITANCE":
            out.append(f"{a} --|> {b}{suffix}")
            continue
        arrow = {"AGGREGATION": "o--", "COMPOSITION": "*--"}.get(kind, "--")
        fc, tc = r.get("from_cardinality"), r.get("to_cardinality")
        left = f' "{fc}"' if fc else ""
        right = f' "{tc}" ' if tc else " "
        out.append(f"{a}{left} {arrow}{right}{b}{suffix}")
    out.append("@enduml")
    return "\n".join(out) + "\n"


def _next_id(prefix: str, taken: set[str]) -> str:
    n = 1
    while f"{prefix}-{n:03d}" in taken:
        n += 1
    return f"{prefix}-{n:03d}"


def normalize(content: dict[str, Any], previous: Any = None) -> dict[str, Any]:
    """Assign stable ids (kept by name from the previous content) and render the diagram."""
    model = dict(model_of(content))
    prev = model_of(previous)
    prev_ent = {e.get("name"): e.get("id") for e in _list(prev.get("entities"))
                if isinstance(e.get("id"), str)}
    taken: set[str] = set()
    ents = []
    for e in _list(model.get("entities")):
        e = dict(e)
        cand = e.get("id") if isinstance(e.get("id"), str) else None
        if not cand or cand in taken or not cand.startswith("ENT-"):
            cand = prev_ent.get(e.get("name"))
        if not cand or cand in taken:
            cand = _next_id("ENT", taken | set(prev_ent.values()))
        taken.add(cand)
        e["id"] = cand
        e["kind"] = str(e.get("kind") or "ENTITY").upper()
        ents.append(e)
    rels, rtaken = [], set()
    for r in _list(model.get("relationships")):
        r = dict(r)
        if not isinstance(r.get("id"), str) or r["id"] in rtaken:
            r["id"] = _next_id("REL", rtaken)
        rtaken.add(r["id"])
        r["kind"] = str(r.get("kind") or "ASSOCIATION").upper()
        rels.append(r)
    rules, btaken = [], set()
    for r in _list(model.get("business_rules")):
        r = dict(r)
        if not isinstance(r.get("id"), str) or r["id"] in btaken:
            r["id"] = _next_id("BR", btaken)
        btaken.add(r["id"])
        rules.append(r)
    model.update(entities=ents, relationships=rels, business_rules=rules)
    req_ids = sorted({x for e in ents for x in (e.get("requirement_ids") or [])
                      if isinstance(x, str)})
    diagram = {"id": DIAGRAM_ID, "title": "Domain Model",
               "plantuml": render_plantuml(model), "requirement_ids": req_ids,
               "component_ids": []}
    return {"model": model, "diagrams": [diagram]}


def rerender_if_model_changed(new: dict[str, Any], old: Any) -> dict[str, Any]:
    """On edit: if the structured model changed, rebuild the diagram from it. A change that
    touches only the PlantUML source is kept as the user's own (and validated as such)."""
    if model_of(new) != model_of(old) and model_of(new):
        fresh = normalize(new, old)
        diagrams = fresh["diagrams"]
        old_d = _list(new.get("diagrams"))
        if old_d:  # keep the diagram id/title/links the user may have set
            diagrams[0] = {**old_d[0], "plantuml": diagrams[0]["plantuml"]}
        return {**new, "model": fresh["model"], "diagrams": diagrams}
    return new
