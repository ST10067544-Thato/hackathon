import json
from dataclasses import replace

import pytest
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat

from creator_companion import agents as agents_module
from creator_companion.agents import WEB_SCOUT_ID, build_team
from creator_companion.tools import web_scout
from creator_companion.tools.web_scout import PageFindings, WebScoutTools, validate_public_url


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "file:///etc/passwd", "http://localhost:7777/health", "http://127.0.0.1/", "http://10.0.0.5/", "http://[::1]/", "http://foo.local/"],
)
def test_non_public_urls_are_rejected(url):
    assert validate_public_url(url) is not None


@pytest.mark.parametrize("url", ["https://www.instagram.com/nasa/", "http://example.com/page?x=1", "https://93.184.216.34/"])
def test_public_urls_are_accepted(url):
    assert validate_public_url(url) is None


async def test_browse_page_refuses_bad_url_without_touching_a_browser(settings, monkeypatch):
    called = []
    monkeypatch.setattr(web_scout, "browser_available", lambda: (called.append(1), True)[1])
    tools = WebScoutTools(settings)

    result = json.loads(await tools.abrowse_page("http://localhost:7777/", "anything"))

    assert result["code"] == "invalid_url"
    assert called == []


async def test_browse_page_reports_missing_browser_extra(settings, monkeypatch):
    monkeypatch.setattr(web_scout, "browser_available", lambda: False)
    tools = WebScoutTools(settings)

    result = json.loads(await tools.abrowse_page("https://example.com", "what is on it"))

    assert result["code"] == "browser_not_installed"
    assert "uv sync --extra browser" in result["hint"]


async def test_browse_page_returns_structured_findings(settings, monkeypatch):
    monkeypatch.setattr(web_scout, "browser_available", lambda: True)
    tools = WebScoutTools(settings)

    async def fake_run(url, goal):
        assert url == "https://example.com/profile" and goal == "formats of the last posts"
        return {
            "url": url,
            "final_url": url,
            "pages_visited": 1,
            "steps": 4,
            "completed": True,
            "findings": PageFindings(page_title="Example", answer="Mostly reels.", key_points=["3 reels"], metrics={"followers": "12.4K"}).model_dump(),
            "errors": [],
        }

    monkeypatch.setattr(tools, "_run", fake_run)

    result = json.loads(await tools.abrowse_page("https://example.com/profile", "formats of the last posts"))

    assert result["findings"]["metrics"]["followers"] == "12.4K"
    assert result["completed"] is True


async def test_browse_page_times_out_cleanly(settings, monkeypatch):
    import asyncio

    monkeypatch.setattr(web_scout, "browser_available", lambda: True)
    tools = WebScoutTools(settings, timeout_seconds=0.01)

    async def slow_run(url, goal):
        await asyncio.sleep(0.2)

    async def guarded(url, goal):
        return await asyncio.wait_for(slow_run(url, goal), timeout=tools.timeout_seconds)

    monkeypatch.setattr(tools, "_run", guarded)

    result = json.loads(await tools.abrowse_page("https://example.com", "slow"))

    assert result["code"] == "timeout"


def test_web_scout_member_is_optional(settings, workspace, zernio_client, tmp_path, monkeypatch):
    db = SqliteDb(db_file=str(tmp_path / "agno.db"))
    model = OpenAIChat(id="gpt-test", api_key="sk-test")

    off = build_team(replace(settings, browser_scout="off"), db, workspace, zernio=zernio_client, model=model)
    assert off.web_scout is None
    assert [m.id for m in off.team.members] == [m.id for m in off.members]
    assert WEB_SCOUT_ID not in [m.id for m in off.team.members]

    on = build_team(replace(settings, browser_scout="on"), db, workspace, zernio=zernio_client, model=model)
    assert on.web_scout is not None
    assert on.team.members[-1].id == WEB_SCOUT_ID
    assert {n for tk in on.web_scout.tools for n in tk.functions} == {"browse_page"}
    assert {n for tk in on.web_scout.tools for n in tk.async_functions} == {"browse_page"}

    monkeypatch.setattr(agents_module, "browser_available", lambda: False)
    auto = build_team(replace(settings, browser_scout="auto"), db, workspace, zernio=zernio_client, model=model)
    assert auto.web_scout is None


def test_llm_prefers_browser_use_key_when_present(settings):
    from browser_use.llm.browser_use.chat import ChatBrowserUse
    from browser_use.llm.openrouter.chat import ChatOpenRouter

    with_key = WebScoutTools(replace(settings, browser_use_api_key="bu_test", model_provider="openrouter", browser_model_id="google/gemma-4-31b-it:free"))
    assert isinstance(with_key._llm(), ChatBrowserUse)
    fallback = with_key._fallback_llm()
    assert isinstance(fallback, ChatOpenRouter) and fallback.model == "google/gemma-4-31b-it:free"

    without = WebScoutTools(replace(settings, model_provider="openrouter", openrouter_api_key="sk-or-test"))
    assert isinstance(without._llm(), ChatOpenRouter)
    assert without._fallback_llm() is None


def test_cloud_browser_requires_key(settings):
    from browser_use import BrowserProfile

    local = WebScoutTools(replace(settings, browser_use_cloud=True, browser_use_api_key=None))._browser_profile(BrowserProfile)
    assert local.use_cloud is False and local.headless is True

    cloud = WebScoutTools(replace(settings, browser_use_cloud=True, browser_use_api_key="bu_test"))._browser_profile(BrowserProfile)
    assert cloud.use_cloud is True
