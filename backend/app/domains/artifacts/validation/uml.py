"""Deterministic validation of PlantUML class and sequence diagrams.

Two layers are used:

1. A built-in structural checker (always runs). It verifies the @startuml /
   @enduml envelope, balanced braces and sequence blocks, and diagram specific
   rules (declared classes, duplicate declarations, relationship endpoints,
   participants and messages). Lines it cannot classify are reported as
   warnings because it is not a full PlantUML grammar.
2. The real PlantUML syntax checker (``plantuml -syntax``), when the command
   configured in ``PLANTUML_COMMAND`` is installed. Its verdict is reported as
   errors. If it is not installed the check is recorded as skipped.
"""

import re
import subprocess
from typing import Any

from app.domains.artifacts import uml_render

from .result import Report, ValidationContext, as_list, is_blank

_NAME = r'(?:"[^"]+"|[A-Za-z_][\w.]*)'
_DASH = r"-{1,2}(?:\[[^\]]*\])?"
_SEQ_ARROW = (
    rf"(?:[ox]?<{{1,2}}[\\/]?{_DASH}|{_DASH}[\\/]?>{{1,2}}[ox]?|{_DASH}[\\/]{{1,2}}"
    rf"|[\\/]{{1,2}}{_DASH}|{_DASH}[ox])"
)
SEQ_MESSAGE = re.compile(
    rf"^(?P<a>{_NAME}|\[|\])?\s*(?P<arrow>{_SEQ_ARROW})\s*(?P<b>{_NAME}|\[|\])?\s*(?::.*)?$"
)
SEQ_PARTICIPANT = re.compile(
    rf"^(participant|actor|boundary|control|entity|database|collections|queue)\s+"
    rf"(?P<name>{_NAME})(?:\s+as\s+(?P<alias>{_NAME}))?(?:\s+<<.*>>)?(?:\s+#\w+)?\s*$",
    re.I,
)
SEQ_PARTICIPANT_ALIAS_FIRST = re.compile(
    r"^(participant|actor|boundary|control|entity|database|collections|queue)\s+"
    r'(?P<long>"[^"]+")\s+as\s+(?P<alias>[A-Za-z_]\w*)\s*$',
    re.I,
)
SEQ_OPEN = re.compile(r"^(alt|opt|loop|par|critical|break|group|box)\b", re.I)
SEQ_MID = re.compile(r"^(else|and)\b", re.I)
SEQ_OTHER = re.compile(
    r"^(activate|deactivate|destroy|create|return|autonumber|title|skinparam|hide|show|"
    r"header|footer|ref\b|newpage|\|\|\||\.\.\.|==|\{|\}|!|delay|\.\.|participant|actor|"
    r"note|hnote|rnote|legend|center|footbox|scale)",
    re.I,
)

CLS_DECL = re.compile(
    r"^(?P<kw>abstract\s+class|abstract|class|interface|enum|annotation|entity|struct)\s+"
    r'(?P<name>"[^"]+"\s+as\s+[A-Za-z_]\w*|[A-Za-z_][\w.]*)(?P<rest>.*)$',
    re.I,
)
_CLS_ARROW = r"[<|*o#x+^}{]{0,2}(?:-+|\.+)(?:\w+(?:-+|\.+))?[>|*o#x+^}{]{0,2}"
CLS_REL = re.compile(
    rf'^(?P<a>"[^"]+"|[A-Za-z_][\w.]*)\s*(?:"[^"]*"\s*)?(?P<arrow>{_CLS_ARROW})\s*'
    rf'(?:"[^"]*"\s*)?(?P<b>"[^"]+"|[A-Za-z_][\w.]*)\s*(?::.*)?$'
)
CLS_MEMBER = re.compile(r"^[A-Za-z_][\w.]*\s*:\s*\S")
CLS_CONTAINER = re.compile(
    r"^(package|namespace|rectangle|node|folder|frame|cloud|database|together)\b", re.I
)
CLS_OTHER = re.compile(
    r"^(title|skinparam|hide|show|left to right direction|top to bottom direction|set\b|"
    r"header|footer|legend|scale|allowmixing|note|hnote|rnote|!|remove|together|\}|namespace)",
    re.I,
)


def _clean(name: str | None) -> str | None:
    if name is None:
        return None
    return name.strip().strip('"')


def _preprocess(src: str) -> list[tuple[int, str]]:
    """Return (line_number, text) for meaningful lines, dropping comments."""
    out: list[tuple[int, str]] = []
    in_block_comment = False
    for no, raw in enumerate(src.splitlines(), start=1):
        line = raw.strip()
        if in_block_comment:
            if "'/" in line:
                in_block_comment = False
            continue
        if line.startswith("/'"):
            if "'/" not in line:
                in_block_comment = True
            continue
        if not line or line.startswith("'"):
            continue
        out.append((no, line))
    return out


def _run_plantuml_cli(src: str, r: Report, path: str) -> None:
    exe = uml_render.locate()
    if not exe:
        r.check(f"plantuml_cli_skipped:{path} (PlantUML not installed)")
        return
    r.check(f"plantuml_cli:{path}")
    try:
        ok, msg, line = uml_render.check_syntax(exe, src)
    except (subprocess.TimeoutExpired, OSError) as exc:
        r.warning("UML_CLI_UNAVAILABLE", f"PlantUML CLI could not run: {exc}", path)
        return
    if not ok:
        r.error("UML_SYNTAX_CLI",
                f"PlantUML reported a syntax error{f' at line {line}' if line else ''}: {msg}",
                path, "Fix the syntax shown and re-validate.")


def _check_envelope(lines: list[tuple[int, str]], r: Report, path: str) -> list[tuple[int, str]]:
    starts = [n for n, t in lines if t.lower().startswith("@startuml")]
    ends = [n for n, t in lines if t.lower().startswith("@enduml")]
    if len(starts) != 1 or lines[0][1].lower().split()[0] != "@startuml":
        r.error("UML_START_MISSING", "Diagram must start with exactly one @startuml.", path,
                "Begin the diagram with '@startuml'.")
    if len(ends) != 1 or lines[-1][1].lower() != "@enduml":
        r.error("UML_END_MISSING", "Diagram must end with exactly one @enduml.", path,
                "End the diagram with '@enduml'.")
    return [(n, t) for n, t in lines if not t.lower().startswith(("@startuml", "@enduml"))]


def declared_class_names(src: str) -> set[str]:
    out: set[str] = set()
    for _no, line in _preprocess(src):
        m = CLS_DECL.match(line)
        if m:
            raw = m.group("name")
            out.add(raw.split(" as ")[-1].strip() if " as " in raw else raw)
    return out


def _check_class(body: list[tuple[int, str]], r: Report, path: str) -> None:
    declared: dict[str, int] = {}
    used: dict[str, int] = {}
    stack: list[str] = []
    rel_count = 0
    in_note = False
    for no, line in body:
        low = line.lower()
        if in_note:
            if low in ("end note", "endnote") or low.startswith(("end legend", "endlegend")):
                in_note = False
            continue
        if re.match(r"^(r?note|hnote|legend)\b", low) and ":" not in line:
            in_note = True
            continue
        if line == "}":
            if not stack:
                r.error("UML_BRACE_UNBALANCED", f"Line {no}: '}}' without matching '{{'.", path)
            else:
                stack.pop()
            continue
        if stack and stack[-1] == "class":
            if line.endswith("{") and not line.startswith(("{static}", "{abstract}")):
                stack.append("class")
            continue  # member line
        m = CLS_DECL.match(line)
        if m:
            raw = m.group("name")
            name = raw.split(" as ")[-1].strip() if " as " in raw else raw
            if name in declared:
                r.error("UML_CLASS_DUPLICATE",
                        f"Line {no}: '{name}' is declared twice (first at line {declared[name]}).",
                        path, "Declare each class once.")
            else:
                declared[name] = no
            if line.rstrip().endswith("{"):
                stack.append("class")
            continue
        if CLS_CONTAINER.match(line) and line.endswith("{"):
            stack.append("container")
            continue
        m = CLS_REL.match(line)
        if m and ("-" in m.group("arrow") or "." in m.group("arrow")):
            rel_count += 1
            for g in ("a", "b"):
                nm = _clean(m.group(g))
                used.setdefault(nm, no)
            continue
        if CLS_MEMBER.match(line):
            used.setdefault(line.split(":")[0].strip(), no)
            continue
        if CLS_OTHER.match(line):
            if line.endswith("{"):
                stack.append("container")
            continue
        r.warning("UML_LINE_UNRECOGNIZED", f"Line {no}: could not classify '{line[:60]}'.", path)
    if stack:
        r.error("UML_BRACE_UNBALANCED", f"{len(stack)} unclosed '{{' block(s).", path,
                "Add the missing '}'.")
    if not declared:
        r.error("UML_NO_CLASSES", "Class diagram declares no classes or interfaces.", path)
    for name, no in used.items():
        if name not in declared:
            r.warning("UML_CLASS_UNDECLARED",
                      f"Line {no}: '{name}' is used but never declared.", path,
                      f"Declare it with 'class {name}'.")
    if declared and rel_count == 0 and len(declared) > 1:
        r.warning("UML_NO_RELATIONSHIPS", "Classes are declared but none are related.", path)
    elif rel_count:
        for name in declared:
            if name not in used:
                r.warning("UML_CLASS_ISOLATED",
                          f"Class '{name}' has no relationship to any other class.", path,
                          "Relate it to the rest of the model or remove it.")


def _check_sequence(body: list[tuple[int, str]], r: Report, path: str) -> None:
    declared: set[str] = set()
    used: dict[str, int] = {}
    blocks: list[str] = []
    messages = 0
    in_note = False
    for no, line in body:
        low = line.lower()
        if in_note:
            if low in ("end note", "endnote", "end legend", "endlegend"):
                in_note = False
            continue
        if re.match(r"^(r?note|hnote|legend)\b", low) and ":" not in line:
            in_note = True
            continue
        if low == "end" or low.startswith("end "):
            if low.startswith(("end note", "end legend")):
                continue
            if not blocks:
                r.error("UML_BLOCK_UNBALANCED", f"Line {no}: 'end' without an open block.", path)
            else:
                blocks.pop()
            continue
        if SEQ_MID.match(line):
            if not blocks:
                r.error("UML_BLOCK_UNBALANCED", f"Line {no}: '{line.split()[0]}' outside a block.",
                        path)
            continue
        m = SEQ_PARTICIPANT_ALIAS_FIRST.match(line) or SEQ_PARTICIPANT.match(line)
        if m:
            declared.add(_clean(m.groupdict().get("name") or m.group("long")))
            if m.groupdict().get("alias"):
                declared.add(_clean(m.group("alias")))
            continue
        if SEQ_OPEN.match(line):
            blocks.append(line.split()[0].lower())
            continue
        m = SEQ_MESSAGE.match(line)
        if m and (m.group("a") or m.group("b")):
            messages += 1
            for g in ("a", "b"):
                nm = _clean(m.group(g))
                if nm and nm not in "[]":
                    used.setdefault(nm, no)
            continue
        if SEQ_OTHER.match(line):
            continue
        r.warning("UML_LINE_UNRECOGNIZED", f"Line {no}: could not classify '{line[:60]}'.", path)
    if blocks:
        r.error("UML_BLOCK_UNBALANCED", f"{len(blocks)} block(s) are missing 'end'.", path,
                "Close every alt/opt/loop/par/group with 'end'.")
    if messages == 0:
        r.error("UML_NO_MESSAGES", "Sequence diagram contains no messages.", path,
                "Add messages such as 'A -> B : request'.")
    participants = declared | set(used)
    if messages and len(participants) < 2:
        r.error("UML_PARTICIPANTS", "Sequence diagram needs at least two participants.", path)
    for name, no in used.items():
        if name not in declared:
            r.warning("UML_PARTICIPANT_UNDECLARED",
                      f"Line {no}: '{name}' is used but not declared as a participant.", path,
                      f"Add 'participant {name}'.")


def validate_plantuml(src: Any, kind: str, path: str, r: Report) -> None:
    """Validate one PlantUML source string; kind is 'class' or 'sequence'."""
    if is_blank(src):
        r.error("UML_SOURCE_MISSING", "PlantUML source is empty.", path,
                "Provide diagram source text.")
        return
    lines = _preprocess(src)
    if not lines:
        r.error("UML_SOURCE_MISSING", "PlantUML source is empty.", path)
        return
    body = _check_envelope(lines, r, path)
    if kind == "class":
        _check_class(body, r, path)
    else:
        _check_sequence(body, r, path)
    _run_plantuml_cli(src, r, path)


def validate_uml(content: dict[str, Any], ctx: ValidationContext, kind: str) -> Report:
    r = Report()
    r.check("structure")
    diagrams = content.get("diagrams")
    if not isinstance(diagrams, list) or not diagrams:
        r.error("UML_EMPTY", "'diagrams' must be a non-empty list.", "diagrams")
        return r
    r.check("plantuml_syntax")
    r.check("diagram_references")
    seen: set[str] = set()
    for i, d in enumerate(diagrams):
        p = f"diagrams[{i}]"
        if not isinstance(d, dict):
            r.error("UML_DIAGRAM_NOT_OBJECT", "Diagram entry is not an object.", p)
            continue
        did = d.get("id")
        if is_blank(did):
            r.error("UML_ID_MISSING", "Diagram has no id.", f"{p}.id")
        elif did in seen:
            r.error("UML_ID_DUPLICATE", f"Diagram id '{did}' is duplicated.", f"{p}.id")
        else:
            seen.add(did)
        if is_blank(d.get("title")):
            r.error("UML_TITLE_MISSING", f"{did or p}: title is missing.", f"{p}.title")
        validate_plantuml(d.get("plantuml"), kind, f"{p}.plantuml", r)
        for rid in as_list(d.get("requirement_ids")):
            if ctx.requirements is not None and rid not in ctx.requirements:
                r.error("UML_REQUIREMENT_UNKNOWN", f"{did or p}: unknown requirement '{rid}'.",
                        f"{p}.requirement_ids")
        for eid in as_list(d.get("domain_entity_ids")):
            if ctx.domain_entities is not None and eid not in ctx.domain_entities:
                r.error("UML_DOMAIN_ENTITY_UNKNOWN",
                        f"{did or p}: unknown domain entity '{eid}'.", f"{p}.domain_entity_ids")
        for cid in as_list(d.get("component_ids")):
            if ctx.components is not None and cid not in ctx.components:
                r.error("UML_COMPONENT_UNKNOWN", f"{did or p}: unknown component '{cid}'.",
                        f"{p}.component_ids")
        if not as_list(d.get("requirement_ids")) and not as_list(d.get("component_ids")):
            r.warning("UML_UNTRACED",
                      f"{did or p}: diagram is not linked to any requirement or component.", p)
    if kind == "class" and ctx.domain_entities:
        declared: set[str] = set()
        for d in diagrams:
            if isinstance(d, dict) and isinstance(d.get("plantuml"), str):
                declared |= declared_class_names(d["plantuml"])
        for eid, ent in ctx.domain_entities.items():
            if str(ent.get("name")) not in declared:
                r.warning("UML_DOMAIN_ENTITY_MISSING",
                          f"Domain entity {ent.get('name')} ({eid}) does not appear in any class "
                          "diagram.", "diagrams", "Add the class or explain why it is omitted.")
    return r
