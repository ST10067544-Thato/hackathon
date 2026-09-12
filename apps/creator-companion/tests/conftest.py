import json
from pathlib import Path

import httpx
import pytest
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat

from creator_companion.agents import build_team
from creator_companion.config import Settings
from creator_companion.tools.workspace import Workspace
from creator_companion.zernio import ZernioClient


class FakeZernio:
    """Records requests and serves canned responses keyed by (METHOD, path)."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: dict[tuple[str, str], tuple[int, object]] = {}

    def respond(self, method: str, path: str, status: int = 200, body: object = None) -> None:
        self.responses[(method.upper(), path)] = (status, body)

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            key = (request.method.upper(), request.url.path)
            status, body = self.responses.get(key, (404, {"error": "not_found", "message": f"no stub for {key}"}))
            if body is None:
                return httpx.Response(status)
            return httpx.Response(status, json=body)

        return httpx.MockTransport(handler)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> dict:
        return json.loads(self.last.content.decode())


@pytest.fixture
def fake_zernio() -> FakeZernio:
    return FakeZernio()


@pytest.fixture
def zernio_client(fake_zernio: FakeZernio) -> ZernioClient:
    return ZernioClient("sk_test", base_url="https://zernio.test/api/v1", transport=fake_zernio.transport())


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace.db")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        model_provider="openai",
        model_id="gpt-test",
        openai_api_key="sk-test",
        openrouter_api_key=None,
        google_api_key=None,
        exa_api_key=None,
        zernio_api_key="sk_test",
        zernio_base_url="https://zernio.test/api/v1",
        zernio_webhook_secret="whsec_test",
        zernio_profile_id=None,
        database_url=None,
        sqlite_path=tmp_path / "agno.db",
        host="127.0.0.1",
        port=7777,
        browser_scout="off",
        browser_headless=True,
        browser_max_steps=3,
        browser_timeout_seconds=5.0,
        browser_use_api_key=None,
        browser_use_cloud=False,
        browser_model_id="gpt-test",
        browser_max_completion_tokens=1024,
        browser_vision=True,
    )


@pytest.fixture
def companion(settings: Settings, workspace: Workspace, zernio_client: ZernioClient, tmp_path: Path):
    db = SqliteDb(db_file=str(tmp_path / "agno.db"))
    return build_team(settings, db, workspace, zernio=zernio_client, model=OpenAIChat(id="gpt-test", api_key="sk-test"))
