"""AgentOS entrypoint.

Run with ``uv run creator-companion`` (or ``npm run dev:agents`` from the repo root).
The FastAPI object is also exposed as ``creator_companion.app:app`` for uvicorn.
"""

from __future__ import annotations

import logging
from typing import Optional

from agno.db.base import BaseDb
from agno.db.sqlite import SqliteDb
from agno.os import AgentOS
from agno.os.interfaces.agui import AGUI
from fastapi import FastAPI

from creator_companion.agents import CreatorCompanion, build_team
from creator_companion.config import Settings
from creator_companion.tools.workspace import Workspace
from creator_companion.webhooks import create_base_app

log = logging.getLogger("creator_companion")


def build_db(settings: Settings) -> BaseDb:
    if settings.database_url:
        from agno.db.postgres import PostgresDb  # optional dependency: creator-companion[postgres]

        return PostgresDb(db_url=settings.database_url)
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteDb(db_file=str(settings.sqlite_path))


def create_agent_os(settings: Optional[Settings] = None) -> tuple[AgentOS, CreatorCompanion]:
    settings = settings or Settings.load()
    db = build_db(settings)
    # The workspace keeps its own SQLite file so its sqlite3 writes never contend
    # with Agno's SQLAlchemy session writes.
    workspace = Workspace(settings.sqlite_path.with_name("workspace.db"))
    companion = build_team(settings, db, workspace)

    if not settings.zernio_api_key:
        log.warning("ZERNIO_API_KEY is not set; Zernio tools will report not_configured until it is.")
    if not settings.zernio_webhook_secret:
        log.warning("ZERNIO_WEBHOOK_SECRET is not set; POST /webhooks/zernio will answer 503.")
    if companion.web_scout is None:
        log.warning("Web Scout is disabled (install with `uv sync --extra browser`, or set BROWSER_SCOUT=on/off).")

    agent_os = AgentOS(
        id="creator-companion-os",
        name="Creator Companion",
        description="Agents that live in a creator's social inbox: monitor, triage, and plan.",
        db=db,
        teams=[companion.team],
        agents=companion.members,
        # AG-UI endpoints for the CopilotKit web app (apps/web): the team at
        # POST /agui, each member under /members/<id>/agui.
        interfaces=[AGUI(team=companion.team)]
        + [AGUI(agent=member, prefix=f"/members/{member.id}") for member in companion.members],
        base_app=create_base_app(companion, settings),
        scheduler=True,
        scheduler_poll_interval=15,
        scheduler_base_url=f"http://127.0.0.1:{settings.port}",
        telemetry=False,
    )
    return agent_os, companion


def create_app() -> FastAPI:
    agent_os, _ = create_agent_os()
    return agent_os.get_app()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.load()
    agent_os, _ = create_agent_os(settings)
    agent_os.serve(app=agent_os.get_app(), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
