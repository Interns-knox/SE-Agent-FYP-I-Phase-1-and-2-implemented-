"""Backend for the browser verification (frontend/scripts/verify-ui.mjs).

Runs the real FastAPI app, routers, services and validators on a throw-away SQLite file.
Only the language model is replaced by a scripted test double that returns valid artifacts
for the project's real feature ids. PlantUML rendering uses the real local renderer.

    python -m tests.e2e.server            # listens on :8001
"""

import os
import re
import sys

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("CORS_ORIGINS", "http://localhost:5174,http://localhost:5173")

import app.domains.artifacts.models  # noqa: E402,F401
import app.domains.features.models  # noqa: E402,F401
import app.domains.workspace.models  # noqa: E402,F401
from app.database import Base, get_db  # noqa: E402
from app.domains.artifacts.router import get_provider  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.api.helpers import (  # noqa: E402
    ARCHITECTURE,
    CLASS_DIAGRAMS,
    DOMAIN_MODEL,
    SEQUENCE_DIAGRAMS,
    SRS_NARRATIVE,
    requirements_payload,
)
from tests.conftest import ScriptedProvider  # noqa: E402


class E2EProvider(ScriptedProvider):
    def generate(self, prompt: str) -> str:
        if "software requirements analyst" in prompt:
            self.set("FEATURES", {"features": [
                {"name": "Accounts", "description": "Registration and login"},
                {"name": "Reports", "description": "Create and list reports"},
                {"name": "Export", "description": "Export reports"}]})
        elif "Derive structured requirements" in prompt:
            fids = re.findall(r'"id"\s*:\s*"([0-9a-f-]{36})"', prompt)
            self.set("REQUIREMENTS", requirements_payload(fids))
        else:
            self.set("SRS", SRS_NARRATIVE)
            self.set("ARCHITECTURE", ARCHITECTURE)
            self.set("DOMAIN_MODEL", DOMAIN_MODEL)
            self.set("UML_CLASS", CLASS_DIAGRAMS)
            self.set("UML_SEQUENCE", SEQUENCE_DIAGRAMS)
            self.set("CRITIQUE", "- looks fine")
        return super().generate(prompt)


def build_app():
    path = os.environ.get("E2E_DB", "/tmp/se_agent_e2e.db")
    if os.path.exists(path):
        os.remove(path)  # always start from an empty database
    # a file database with one connection per session: the browser sends parallel requests
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False,
                                                              "timeout": 30})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def db():
        s = session()
        try:
            yield s
        finally:
            s.close()

    provider = E2EProvider()
    app = create_app()
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_provider] = lambda: provider
    # the real app's default LLM provider is also used by Phase 1 feature extraction
    import app.domains.workspace.router as ws
    ws.get_llm_provider = lambda: provider
    return app


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    uvicorn.run(build_app(), host="127.0.0.1", port=port, log_level="warning")
