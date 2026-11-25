"""Deterministic validation of the ARCHITECTURE artifact."""

import re
from typing import Any

from .result import Report, ValidationContext, as_list, is_blank

COMP_ID = re.compile(r"^CMP-\d{3,}$")


def validate_architecture(content: dict[str, Any], ctx: ValidationContext) -> Report:
    r = Report()
    r.check("structure")
    if is_blank(content.get("style")):
        r.warning("ARCH_STYLE_MISSING", "Architectural style is not stated.", "style")
    comps = content.get("components")
    if not isinstance(comps, list) or not comps:
        r.error("ARCH_EMPTY", "'components' must be a non-empty list.", "components")
        return r

    seen: dict[str, int] = {}
    names: set[str] = set()
    r.check("component_fields")
    r.check("component_ids")
    for i, c in enumerate(comps):
        p = f"components[{i}]"
        if not isinstance(c, dict):
            r.error("ARCH_NOT_OBJECT", "Component entry is not an object.", p)
            continue
        cid = c.get("id")
        if is_blank(cid):
            r.error("ARCH_ID_MISSING", "Component has no id.", f"{p}.id", "Use CMP-001 style ids.")
        else:
            if not COMP_ID.match(cid):
                r.error("ARCH_ID_FORMAT", f"Component id '{cid}' must match CMP-###.", f"{p}.id")
            if cid in seen:
                r.error("ARCH_ID_DUPLICATE", f"Component id '{cid}' is duplicated.", f"{p}.id")
            else:
                seen[cid] = i
        name = c.get("name")
        if is_blank(name):
            r.error("ARCH_NAME_MISSING", f"{cid or p}: name is missing.", f"{p}.name")
        elif name.strip().casefold() in names:
            r.error("ARCH_NAME_DUPLICATE", f"Component name '{name}' is duplicated.", f"{p}.name")
        else:
            names.add(name.strip().casefold())
        if is_blank(c.get("responsibility")):
            r.error("ARCH_RESPONSIBILITY_MISSING", f"{cid or p}: responsibility is missing.",
                    f"{p}.responsibility", "State what the component is responsible for.")

    r.check("dependencies")
    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        for d in as_list(c.get("depends_on")):
            if d not in seen:
                r.error("ARCH_DEPENDENCY_UNKNOWN",
                        f"{cid or i}: depends on unknown component '{d}'.",
                        f"components[{i}].depends_on")
            elif d == cid:
                r.error("ARCH_DEPENDENCY_SELF", f"{cid}: depends on itself.",
                        f"components[{i}].depends_on")

    r.check("requirement_links")
    covered: set[str] = set()
    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            continue
        reqs = as_list(c.get("requirement_ids"))
        if not reqs:
            r.warning("ARCH_COMPONENT_UNTRACED",
                      f"{c.get('id') or i}: component is not linked to any requirement.",
                      f"components[{i}].requirement_ids")
        if len(set(reqs)) != len(reqs):
            r.warning("ARCH_REQUIREMENT_REF_DUPLICATE",
                      f"{c.get('id') or i}: duplicate requirement references.",
                      f"components[{i}].requirement_ids")
        for rid in reqs:
            if ctx.requirements is not None and rid not in ctx.requirements:
                r.error("ARCH_REQUIREMENT_UNKNOWN",
                        f"{c.get('id') or i}: unknown requirement '{rid}'.",
                        f"components[{i}].requirement_ids")
            covered.add(rid)
    if ctx.requirements is not None:
        r.check("requirement_coverage")
        for rid in ctx.requirements:
            if rid not in covered:
                r.warning("REQ_NOT_IN_ARCHITECTURE",
                          f"Requirement {rid} is not allocated to any component.",
                          "components", "Link it from the component that implements it.")
    return r
