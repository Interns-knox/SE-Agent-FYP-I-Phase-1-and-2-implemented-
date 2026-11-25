"""Requirement identifier rules.

* Functional requirements use FR-###, non-functional requirements NFR-###.
* Ids are assigned by the backend, never trusted from the model: an id is kept only when it
  already belongs to the same requirement in the previous content (same id and type, or the
  same title), otherwise the next number that was never used in ANY earlier version is taken.
* Ids that were used once are never handed out again, even if the requirement was removed.
"""

import re
from typing import Any

FR_RE = re.compile(r"^FR-(\d{3,})$")
NFR_RE = re.compile(r"^NFR-(\d{3,})$")
FUNCTIONAL, NON_FUNCTIONAL = "FUNCTIONAL", "NON_FUNCTIONAL"
SCHEMA_VERSION = 2


def _norm_title(req: dict) -> str:
    t = req.get("title") or req.get("category") or ""
    return re.sub(r"\s+", " ", str(t)).strip().casefold()


def req_list(content: Any) -> list[dict]:
    if not isinstance(content, dict):
        return []
    items = content.get("requirements")
    return [r for r in items if isinstance(r, dict)] if isinstance(items, list) else []


def infer_type(req: dict) -> str:
    t = str(req.get("type") or "").upper().replace("-", "_").replace(" ", "_")
    if t in (FUNCTIONAL, NON_FUNCTIONAL):
        return t
    rid = str(req.get("id") or "")
    if rid.startswith("NFR-") or req.get("category") or req.get("measurable_criterion"):
        return NON_FUNCTIONAL
    return FUNCTIONAL


def historic_ids(snapshots: list[Any], trusted: list[bool] | None = None) -> dict[str, str]:
    """id -> last known title across every stored version (oldest to newest).

    Every version marks its ids as used. Only `trusted` versions (those that passed
    validation) define the title an id stands for, so an invalid draft that reused an id
    cannot rewrite who owns it. An id seen only in untrusted versions has an empty title."""
    out: dict[str, str] = {}
    for i, content in enumerate(snapshots):
        ok = True if trusted is None else trusted[i]
        for r in req_list(content):
            rid = r.get("id")
            if isinstance(rid, str) and rid:
                out[rid] = _norm_title(r) if ok else out.get(rid, "")
    return out


def retired_ids(snapshots: list[Any], current: Any,
                trusted: list[bool] | None = None) -> dict[str, str]:
    """Ids seen in history but missing from `current` (the content being replaced)."""
    now = {r.get("id") for r in req_list(current)}
    return {rid: t for rid, t in historic_ids(snapshots, trusted).items() if rid not in now}


def _number(rid: str) -> int:
    m = FR_RE.match(rid) or NFR_RE.match(rid)
    return int(m.group(1)) if m else 0


def assign_ids(content: dict[str, Any], previous: Any, history: dict[str, str]) -> dict[str, Any]:
    """Return content with normalized types, backend-assigned unique ids and schema_version 2."""
    prev = req_list(previous)
    prev_by_id = {r["id"]: r for r in prev if isinstance(r.get("id"), str)}
    prev_by_title = {_norm_title(r): r["id"] for r in prev if isinstance(r.get("id"), str)}
    taken: set[str] = set()
    counters = {"FR": 0, "NFR": 0}
    for rid in history:
        prefix = "NFR" if rid.startswith("NFR-") else "FR" if rid.startswith("FR-") else None
        if prefix:
            counters[prefix] = max(counters[prefix], _number(rid))
    out: list[dict] = []
    for r in req_list(content):
        r = dict(r)
        kind = infer_type(r)
        prefix = "NFR" if kind == NON_FUNCTIONAL else "FR"
        r["type"] = kind
        claimed = r.get("id") if isinstance(r.get("id"), str) else None
        keep = None
        if claimed and claimed in prev_by_id and infer_type(prev_by_id[claimed]) == kind \
                and claimed not in taken:
            keep = claimed
        else:
            cand = prev_by_title.get(_norm_title(r))
            if cand and cand not in taken and cand.startswith(prefix + "-"):
                keep = cand
        if keep is None:
            counters[prefix] += 1
            keep = f"{prefix}-{counters[prefix]:03d}"
            while keep in taken or keep in history:
                counters[prefix] += 1
                keep = f"{prefix}-{counters[prefix]:03d}"
        taken.add(keep)
        r["id"] = keep
        out.append(r)
    return {**{k: v for k, v in content.items() if k != "requirements"},
            "schema_version": SCHEMA_VERSION, "requirements": out}


def legacy_id_mapping(content: Any, history: dict[str, str]) -> dict[str, str]:
    """Map non FR-/NFR- ids (e.g. REQ-001) to new ids, without touching valid ones."""
    counters = {"FR": 0, "NFR": 0}
    for rid in history:
        if rid.startswith("FR-"):
            counters["FR"] = max(counters["FR"], _number(rid))
        elif rid.startswith("NFR-"):
            counters["NFR"] = max(counters["NFR"], _number(rid))
    mapping: dict[str, str] = {}
    for r in req_list(content):
        rid = r.get("id")
        if isinstance(rid, str) and not (FR_RE.match(rid) or NFR_RE.match(rid)):
            prefix = "NFR" if infer_type(r) == NON_FUNCTIONAL else "FR"
            counters[prefix] += 1
            new = f"{prefix}-{counters[prefix]:03d}"
            while new in history or new in mapping.values():
                counters[prefix] += 1
                new = f"{prefix}-{counters[prefix]:03d}"
            mapping[rid] = new
    return mapping
