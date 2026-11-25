"""Local PlantUML syntax checking and SVG rendering.

Uses the PlantUML command configured in PLANTUML_COMMAND (no external rendering service).
PlantUML draws an "error picture" and exits 0 on bad input, so the syntax check always runs
first and a failing source never yields an image. Sources are restricted (no includes, no
environment access), run under PlantUML's most restrictive security profile, in an empty temporary
directory, with a size and time limit.
"""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from collections import OrderedDict
from typing import Any

from app.config import settings

MAX_SOURCE_CHARS = 200_000
TIMEOUT_SECONDS = 30
_FORBIDDEN = re.compile(
    r"^\s*!\s*(include|includeurl|includesub|includedef|import|theme\s+\S+\s+from)\b"
    r"|%getenv|%load_json|%loadjson|%file\b|%dirpath", re.I | re.M)
_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_CACHE_MAX = 256


def locate() -> str | None:
    cmd = settings.PLANTUML_COMMAND
    return shutil.which(cmd) if cmd else None


def renderer_status() -> dict[str, Any]:
    exe = locate()
    if exe is None:
        return {"available": False, "command": settings.PLANTUML_COMMAND or None,
                "reason": "PlantUML is not installed. Install it and set PLANTUML_COMMAND "
                          "(see README, 'UML rendering')."}
    return {"available": True, "command": exe, "reason": ""}


def run_plantuml(exe: str, args: list[str], source: str) -> subprocess.CompletedProcess:
    # "SANDBOX" is the name PlantUML gives its most restrictive built-in profile
    env = {**os.environ, "PLANTUML_SECURITY_PROFILE": "SANDBOX",
           # the launcher script calls `java`; make the install's own bin directory visible
           "PATH": os.path.dirname(os.path.realpath(exe)) + os.pathsep + os.environ.get("PATH", "")}
    with tempfile.TemporaryDirectory(prefix="se-agent-puml-") as tmp:
        return subprocess.run([exe, *args], input=source, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS, cwd=tmp, env=env)  # noqa: S603


def check_syntax(exe: str, source: str) -> tuple[bool, str, int | None]:
    """(ok, message, line) from `plantuml -syntax`."""
    p = run_plantuml(exe, ["-syntax"], source)
    lines = (p.stdout or "").strip().splitlines()
    if lines and lines[0].strip().upper() == "ERROR":
        line = int(lines[1]) if len(lines) > 1 and lines[1].strip().isdigit() else None
        msg = lines[2].strip() if len(lines) > 2 else "Syntax error"
        return False, msg, line
    if p.returncode != 0 and not lines:
        return False, (p.stderr or "PlantUML failed").strip()[:300], None
    return True, "", None


def render_svg(source: Any) -> dict[str, Any]:
    """{ok, svg?, error?, line?, renderer_available}. Never raises."""
    status = renderer_status()
    base: dict[str, Any] = {"ok": False, "svg": None, "error": None, "line": None,
                            "renderer_available": status["available"], "cached": False}
    if not isinstance(source, str) or not source.strip():
        return {**base, "error": "The PlantUML source is empty."}
    if len(source) > MAX_SOURCE_CHARS:
        return {**base, "error": f"The source is larger than {MAX_SOURCE_CHARS} characters."}
    if "@startuml" not in source or "@enduml" not in source:
        return {**base, "error": "The source must start with @startuml and end with @enduml."}
    m = _FORBIDDEN.search(source)
    if m:
        return {**base, "error": f"'{m.group(0).strip()}' is not allowed (includes and "
                                 "environment access are disabled)."}
    exe = locate()
    if exe is None:
        return {**base, "error": status["reason"]}
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return {**_CACHE[key], "cached": True}
    try:
        ok, msg, line = check_syntax(exe, source)
        if not ok:
            result = {**base, "error": msg, "line": line}
        else:
            p = run_plantuml(exe, ["-tsvg", "-pipe"], source)
            svg = (p.stdout or "").strip()
            if p.returncode != 0 or "<svg" not in svg:
                result = {**base, "error": (p.stderr or "PlantUML produced no image").strip()[:300]}
            else:
                svg = re.sub(r"<script\b.*?</script>", "", svg[svg.index("<svg"):],
                             flags=re.S | re.I)
                result = {**base, "ok": True, "svg": svg}
    except subprocess.TimeoutExpired:
        return {**base, "error": f"Rendering exceeded {TIMEOUT_SECONDS}s and was stopped."}
    except OSError as exc:
        return {**base, "error": f"PlantUML could not be started: {exc}"}
    _CACHE[key] = result
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return result
