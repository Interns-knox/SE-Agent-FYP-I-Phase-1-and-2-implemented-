"""Shared fixtures: in-memory SQLite database + FastAPI TestClient + scripted LLM provider.

The API tests run the real routers, services, ORM models and deterministic
validators. Only the LLM provider is replaced (it needs a live Ollama).
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.domains.artifacts.models  # noqa: F401
import app.domains.features.models  # noqa: F401
import app.domains.workspace.models  # noqa: F401
from app.database import Base, get_db
from app.domains.ai.provider import LLMProvider
from app.domains.artifacts.router import get_provider
from app.main import create_app


class ScriptedProvider(LLMProvider):
    """Returns canned JSON chosen by the artifact kind named in the prompt."""

    def __init__(self):
        self.responses: dict[str, str] = {}
        self.prompts: list[str] = []
        self.fail_with: Exception | None = None

    MARKERS = {
        "Derive structured requirements": "REQUIREMENTS",
        "narrative sections": "SRS",
        "Design a system architecture": "ARCHITECTURE",
        "conceptual DOMAIN MODEL": "DOMAIN_MODEL",
        "UML CLASS diagrams": "UML_CLASS",
        "UML SEQUENCE diagrams": "UML_SEQUENCE",
        "reviewing software architect": "CRITIQUE",
        "software requirements analyst": "FEATURES",
    }

    def set(self, kind: str, payload) -> None:
        self.responses[kind] = payload if isinstance(payload, str) else json.dumps(payload)

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.fail_with is not None:
            raise self.fail_with
        for marker, kind in self.MARKERS.items():
            if marker in prompt:
                return self.responses[kind]
        raise AssertionError("unrecognised prompt")


@pytest.fixture()
def provider():
    return ScriptedProvider()


@pytest.fixture()
def db_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@pytest.fixture()
def client(provider, db_factory, monkeypatch):
    Session = db_factory

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_provider] = lambda: provider
    # Phase 1 extraction calls get_llm_provider() directly.
    monkeypatch.setattr("app.domains.workspace.router.get_llm_provider", lambda: provider)
    monkeypatch.setattr("app.config.settings.PLANTUML_COMMAND", "")
    with TestClient(app) as c:
        yield c
