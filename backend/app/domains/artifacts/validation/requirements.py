"""Deterministic validation of the REQUIREMENTS artifact.

Two content formats are supported:

* schema_version 2 (generated now): functional requirements carry actor, expected behavior
  and optional preconditions; non-functional requirements carry a category and a measurable
  criterion (or an explicit needs_clarification flag when the context gives no target).
* no schema_version (created before the guided workflow): validated as before; the newer
  fields only produce a warning so existing approved artifacts stay usable.
"""

import re
from typing import Any

from .result import Report, ValidationContext, is_blank

REQ_ID = re.compile(r"^(FR|NFR)-\d{3,}$")
PRIORITIES = {"MUST", "SHOULD", "COULD", "WONT"}
TYPES = {"FUNCTIONAL", "NON_FUNCTIONAL"}
NFR_CATEGORIES = {"PERFORMANCE", "SECURITY", "RELIABILITY", "AVAILABILITY", "USABILITY",
                  "MAINTAINABILITY", "SCALABILITY", "PORTABILITY", "COMPLIANCE"}


def _title_key(req: dict) -> str:
    raw = str(req.get("title") or req.get("category") or "")
    return re.sub(r"\s+", " ", raw).strip().casefold()


def validate_requirements(content: dict[str, Any], ctx: ValidationContext) -> Report:
    r = Report()
    reqs = content.get("requirements")
    v2 = content.get("schema_version") == 2
    r.check("structure")
    if not isinstance(reqs, list) or not reqs:
        r.error("REQ_EMPTY", "'requirements' must be a non-empty list.", "requirements",
                "Add at least one functional requirement.")
        return r

    seen: dict[str, int] = {}
    covered_features: set[str] = set()
    n_fr = n_nfr = 0
    legacy_missing = 0
    for check in ("required_fields", "requirement_ids", "acceptance_criteria", "source_features"):
        r.check(check)
    for i, req in enumerate(reqs):
        p = f"requirements[{i}]"
        if not isinstance(req, dict):
            r.error("REQ_NOT_OBJECT", "Requirement entry is not an object.", p)
            continue
        rid = req.get("id")
        label = rid if isinstance(rid, str) and rid else p
        rtype = req.get("type")
        is_nfr = rtype == "NON_FUNCTIONAL"

        # ---- identifier -------------------------------------------------------------
        if is_blank(rid):
            r.error("REQ_ID_MISSING", "Requirement has no id.", f"{p}.id",
                    "Assign an id such as FR-001 or NFR-001.")
        else:
            if not REQ_ID.match(rid):
                legacy = rid.startswith("REQ-")
                r.error("REQ_ID_FORMAT",
                        f"Requirement id '{rid}' must match FR-### or NFR-###.", f"{p}.id",
                        "Use FR-### for functional and NFR-### for non-functional requirements."
                        + (" Use the 'normalize requirement ids' action to migrate REQ- ids."
                           if legacy else ""))
            if rid in seen:
                r.error("REQ_ID_DUPLICATE",
                        f"Requirement id '{rid}' is used at index {seen[rid]} and {i}.",
                        f"{p}.id", "Give every requirement a unique id.")
            else:
                seen[rid] = i
            if rid in ctx.retired_ids:
                if ctx.retired_ids[rid] and ctx.retired_ids[rid] != _title_key(req):
                    r.error("REQ_ID_REUSED",
                            f"Id '{rid}' belonged to a different, since removed requirement "
                            f"('{ctx.retired_ids[rid]}'). Retired ids must not be reused.",
                            f"{p}.id", "Use a new, never used id.")
                else:
                    r.warning("REQ_ID_RESTORED",
                              f"Id '{rid}' restores a previously removed requirement.", f"{p}.id")

        # ---- type ------------------------------------------------------------------------
        if rtype not in TYPES:
            r.error("REQ_TYPE_INVALID", f"{label}: type must be FUNCTIONAL or NON_FUNCTIONAL.",
                    f"{p}.type")
        else:
            if is_nfr:
                n_nfr += 1
            else:
                n_fr += 1
            if isinstance(rid, str) and REQ_ID.match(rid):
                expected = "NFR" if is_nfr else "FR"
                if not rid.startswith(expected + "-"):
                    r.error("REQ_ID_TYPE_MISMATCH",
                            f"{rid}: a {rtype} requirement must use the {expected}- prefix.",
                            f"{p}.id", f"Rename to {expected}-###.")

        # ---- common fields -------------------------------------------------------------
        if is_blank(req.get("title")) and not (v2 and is_nfr):
            r.error("REQ_TITLE_MISSING", f"{label}: title is missing.", f"{p}.title")
        if is_blank(req.get("description")):
            r.error("REQ_DESCRIPTION_MISSING", f"{label}: description is missing.",
                    f"{p}.description", "Describe what the system shall do.")
        if req.get("priority") not in PRIORITIES:
            r.warning("REQ_PRIORITY_INVALID",
                      f"{label}: priority should be one of {sorted(PRIORITIES)}.",
                      f"{p}.priority")
        if (rtype == "FUNCTIONAL" and not is_blank(req.get("description"))
                and not re.search(r"\b(shall|must|should)\b", req["description"], re.I)):
            r.warning("REQ_NOT_NORMATIVE",
                      f"{label}: description does not use 'shall/must/should'.",
                      f"{p}.description")

        # ---- acceptance / measurable criteria ----------------------------------------
        ac = req.get("acceptance_criteria")
        has_ac = isinstance(ac, list) and any(not is_blank(a) for a in ac)
        if v2 and is_nfr:
            crit = req.get("measurable_criterion")
            flagged = req.get("needs_clarification") is True
            if is_blank(crit) and not has_ac and not flagged:
                r.error("REQ_NFR_CRITERION_MISSING",
                        f"{label}: no measurable criterion.", f"{p}.measurable_criterion",
                        "State a measurable target, or set needs_clarification to true with a "
                        "clarification_note if the project context gives no target.")
            elif flagged:
                note = req.get("clarification_note") or "target value not defined in the context"
                r.warning("REQ_NFR_NEEDS_CLARIFICATION",
                          f"{label}: needs human clarification ({note}).",
                          f"{p}.measurable_criterion",
                          "Agree a measurable target and replace the placeholder.")
            elif isinstance(crit, str) and not re.search(r"\d", crit):
                r.warning("REQ_NFR_NOT_MEASURABLE",
                          f"{label}: the criterion contains no number or threshold.",
                          f"{p}.measurable_criterion")
        elif not has_ac:
            r.error("REQ_ACCEPTANCE_MISSING", f"{label}: no acceptance criteria.",
                    f"{p}.acceptance_criteria", "Add at least one testable criterion.")

        # ---- schema v2 specifics ------------------------------------------------------
        if v2 and is_nfr:
            cat = str(req.get("category") or "").upper()
            if is_blank(req.get("category")):
                r.error("REQ_NFR_CATEGORY_MISSING", f"{label}: quality category is missing.",
                        f"{p}.category", f"Use one of {sorted(NFR_CATEGORIES)}.")
            elif cat not in NFR_CATEGORIES:
                r.error("REQ_NFR_CATEGORY_INVALID",
                        f"{label}: category '{req.get('category')}' is not supported.",
                        f"{p}.category", f"Use one of {sorted(NFR_CATEGORIES)}.")
        elif rtype == "FUNCTIONAL":
            missing = [f for f in ("actor", "expected_behavior") if is_blank(req.get(f))]
            if v2:
                for f in missing:
                    code = "REQ_ACTOR_MISSING" if f == "actor" else "REQ_BEHAVIOR_MISSING"
                    r.error(code, f"{label}: {f.replace('_', ' ')} is missing.", f"{p}.{f}",
                            "Name the responsible actor." if f == "actor"
                            else "Describe the observable behavior.")
                pre = req.get("preconditions")
                if pre is not None and not (isinstance(pre, list)
                                            and all(isinstance(x, str) for x in pre)):
                    r.error("REQ_PRECONDITIONS_INVALID",
                            f"{label}: preconditions must be a list of strings.",
                            f"{p}.preconditions")
            elif missing:
                legacy_missing += 1

        # ---- source features ----------------------------------------------------------
        srcs = req.get("source_feature_ids")
        required_src = not (v2 and is_nfr)
        if not isinstance(srcs, list) or not srcs:
            if required_src:
                r.error("REQ_SOURCE_MISSING", f"{label}: no source feature referenced.",
                        f"{p}.source_feature_ids", "Reference at least one approved feature id.")
        else:
            if len(set(map(str, srcs))) != len(srcs):
                r.warning("REQ_SOURCE_DUPLICATE", f"{label}: duplicate feature references.",
                          f"{p}.source_feature_ids")
            for s in srcs:
                s = str(s)
                status = ctx.feature_status.get(s)
                if status is None:
                    r.error("REQ_SOURCE_UNKNOWN",
                            f"{label}: feature '{s}' does not exist in this project.",
                            f"{p}.source_feature_ids")
                elif status != "APPROVED":
                    r.error("REQ_SOURCE_NOT_APPROVED",
                            f"{label}: feature '{s}' is {status}, not APPROVED.",
                            f"{p}.source_feature_ids", "Approve the feature or remove the link.")
                else:
                    covered_features.add(s)

    if legacy_missing:
        r.warning("REQ_LEGACY_FORMAT",
                  f"{legacy_missing} functional requirement(s) lack the newer actor and "
                  "expected_behavior fields (created before schema version 2).", "requirements",
                  "Edit them or regenerate the requirements to add the missing fields.")

    r.check("type_coverage")
    if n_fr == 0:
        r.error("REQ_NO_FUNCTIONAL", "No functional requirements defined.", "requirements")
    if n_nfr == 0:
        r.warning("REQ_NO_NON_FUNCTIONAL", "No non-functional requirements defined.",
                  "requirements", "Add performance, security, usability or similar NFRs.")

    r.check("feature_coverage")
    for fid, status in ctx.feature_status.items():
        if status == "APPROVED" and fid not in covered_features:
            r.warning("FEATURE_UNCOVERED",
                      f"Approved feature {fid} is not referenced by any requirement.",
                      "requirements", "Add a requirement derived from this feature.")
    return r
