"""Route an artifact to its deterministic validator."""

from typing import Any

from app.domains.artifacts.models import ArtifactType

from .architecture import validate_architecture
from .domain_model import validate_domain_model
from .requirements import validate_requirements
from .result import Report, ValidationContext
from .srs import validate_srs
from .uml import validate_uml


def validate_content(
    artifact_type: ArtifactType, content: Any, ctx: ValidationContext
) -> Report:
    if not isinstance(content, dict):
        r = Report()
        r.error("CONTENT_NOT_OBJECT", "Artifact content must be a JSON object.")
        return r
    if artifact_type == ArtifactType.REQUIREMENTS:
        return validate_requirements(content, ctx)
    if artifact_type == ArtifactType.SRS:
        return validate_srs(content, ctx)
    if artifact_type == ArtifactType.ARCHITECTURE:
        return validate_architecture(content, ctx)
    if artifact_type == ArtifactType.DOMAIN_MODEL:
        return validate_domain_model(content, ctx)
    if artifact_type == ArtifactType.UML_CLASS:
        return validate_uml(content, ctx, "class")
    if artifact_type == ArtifactType.UML_SEQUENCE:
        return validate_uml(content, ctx, "sequence")
    raise ValueError(f"Unsupported artifact type {artifact_type}")
