"""Structured result container shared by all deterministic validators."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

PASSED = "PASSED"
PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
FAILED = "FAILED"


@dataclass
class Report:
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    def error(self, code: str, message: str, path: str = "", suggestion: str = "") -> None:
        self.errors.append(
            {"code": code, "severity": "error", "message": message, "path": path,
             "suggestion": suggestion}
        )

    def warning(self, code: str, message: str, path: str = "", suggestion: str = "") -> None:
        self.warnings.append(
            {"code": code, "severity": "warning", "message": message, "path": path,
             "suggestion": suggestion}
        )

    def check(self, name: str) -> None:
        self.checks.append(name)

    def to_dict(self, content_version: int | None = None) -> dict[str, Any]:
        if self.errors:
            status = FAILED
        elif self.warnings:
            status = PASSED_WITH_WARNINGS
        else:
            status = PASSED
        return {
            "validator": "deterministic",
            "status": status,
            "errors": self.errors,
            "warnings": self.warnings,
            "checks_run": self.checks,
            "content_version": content_version,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }


@dataclass
class ValidationContext:
    """Read-only facts about the project used for cross-reference checks."""

    # feature id (str) -> status value
    feature_status: dict[str, str] = field(default_factory=dict)
    # requirement id -> requirement dict (None if no requirements artifact exists)
    requirements: dict[str, dict] | None = None
    # component id -> component dict (None if no architecture artifact exists)
    components: dict[str, dict] | None = None
    # domain model entity id -> entity dict (None if no domain model artifact exists)
    domain_entities: dict[str, dict] | None = None
    # requirement id -> last known title, for ids that existed in an earlier version but are
    # absent from the content being replaced (retired ids must not be silently reused)
    retired_ids: dict[str, str] = field(default_factory=dict)


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def is_blank(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()
