"""Deterministic validation of the SRS artifact."""

from typing import Any

from .result import Report, ValidationContext, as_list, is_blank

REQUIRED_SECTIONS = [
    "purpose",
    "scope",
    "overall_description",
    "functional_requirements",
    "non_functional_requirements",
]


def validate_srs(content: dict[str, Any], ctx: ValidationContext) -> Report:
    r = Report()
    r.check("structure")
    sections = content.get("sections")
    if not isinstance(sections, list) or not sections:
        r.error("SRS_EMPTY", "'sections' must be a non-empty list.", "sections")
        return r
    ids: dict[str, int] = {}
    r.check("section_fields")
    for i, s in enumerate(sections):
        p = f"sections[{i}]"
        if not isinstance(s, dict):
            r.error("SRS_SECTION_NOT_OBJECT", "Section entry is not an object.", p)
            continue
        sid = s.get("id")
        if is_blank(sid):
            r.error("SRS_SECTION_ID_MISSING", "Section has no id.", f"{p}.id")
        elif sid in ids:
            r.error("SRS_SECTION_ID_DUPLICATE", f"Section id '{sid}' is duplicated.", f"{p}.id")
        else:
            ids[sid] = i
        if is_blank(s.get("title")):
            r.error("SRS_SECTION_TITLE_MISSING", f"Section {sid or p} has no title.", f"{p}.title")
        if is_blank(s.get("body")):
            r.error("SRS_SECTION_BODY_EMPTY", f"Section {sid or p} has no body text.",
                    f"{p}.body", "Write the section content.")
    r.check("required_sections")
    for sid in REQUIRED_SECTIONS:
        if sid not in ids:
            r.error("SRS_SECTION_MISSING", f"Required section '{sid}' is missing.", "sections",
                    f"Add a section with id '{sid}'.")

    r.check("requirement_references")
    refs = as_list(content.get("requirement_ids"))
    if not refs:
        r.error("SRS_NO_REQUIREMENT_REFS", "'requirement_ids' is empty.", "requirement_ids")
    if len(set(refs)) != len(refs):
        r.error("SRS_REQUIREMENT_REF_DUPLICATE", "Duplicate ids in 'requirement_ids'.",
                "requirement_ids")
    if ctx.requirements is None:
        r.warning("SRS_NO_REQUIREMENTS_ARTIFACT",
                  "No requirements artifact exists; references cannot be checked.")
    else:
        for rid in refs:
            if rid not in ctx.requirements:
                r.error("SRS_REQUIREMENT_UNKNOWN", f"Unknown requirement id '{rid}'.",
                        "requirement_ids")
        for rid in ctx.requirements:
            if rid not in refs:
                r.error("SRS_REQUIREMENT_OMITTED", f"Requirement {rid} is not in the SRS.",
                        "requirement_ids", "Include every requirement in the SRS.")
    return r
