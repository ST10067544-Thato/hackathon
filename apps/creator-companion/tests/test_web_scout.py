import json
from dataclasses import replace

import pytest
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat

from creator_companion import agents as agents_module
from creator_companion.agents import WEB_SCOUT_ID, build_team
from creator_companion.tools import web_scout
from creator_companion.tools.web_scout import (
    PageFindings,
    WebScoutTools,
    _gateway_rejected,
    _model_quota_exhausted,
    validate_public_url,
)


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


def test_local_browser_is_pinned_to_chromium(settings):
    """Never the developer's own Google Chrome: that profile carries real logins."""
    from browser_use import BrowserProfile

    profile = WebScoutTools(settings)._browser_profile(BrowserProfile)

    assert profile.channel is not None
    assert str(getattr(profile.channel, "value", profile.channel)) == "chromium"


def test_leader_delegates_browsing_only_when_the_scout_exists(settings, workspace, zernio_client, tmp_path):
    """The leader must not claim it cannot browse while Web Scout is a member."""
    db = SqliteDb(db_file=str(tmp_path / "agno.db"))
    model = OpenAIChat(id="gpt-test", api_key="sk-test")

    on = build_team(replace(settings, browser_scout="on"), db, workspace, zernio=zernio_client, model=model)
    said = " ".join(on.team.instructions)
    assert "Web Scout" in said
    assert "Never tell the creator you are unable to visit a website" in said
    # A bare site name must still reach the scout.
    assert "resolve it to the obvious public URL" in said

    off = build_team(replace(settings, browser_scout="off"), db, workspace, zernio=zernio_client, model=model)
    said_off = " ".join(off.team.instructions)
    assert "Web Scout" not in said_off
    assert "no browser in this deployment" in said_off


def test_free_tier_gateway_rejection_is_recognised():
    assert _gateway_rejected(["API request failed: Free tier accounts are not allowed to use the LLM Gateway."])
    assert not _gateway_rejected(["Timeout waiting for selector", "net::ERR_NAME_NOT_RESOLVED"])


async def test_hosted_model_rejection_retries_on_the_provider_model(settings, monkeypatch):
    """A free-tier BROWSER_USE_API_KEY must not end the run with an empty result."""
    from browser_use.llm.browser_use.chat import ChatBrowserUse
    from browser_use.llm.openrouter.chat import ChatOpenRouter

    monkeypatch.setattr(web_scout, "browser_available", lambda: True)
    tools = WebScoutTools(replace(settings, browser_use_api_key="bu_free", model_provider="openrouter", openrouter_api_key="sk-or-test"))

    llms_used = []

    class FakeHistory:
        def __init__(self, done): self._done = done
        def is_done(self): return self._done
        def errors(self): return [] if self._done else ["API request failed: Free tier accounts are not allowed to use the LLM Gateway."]
        def urls(self): return ["https://example.com"]
        def number_of_steps(self): return 3
        structured_output = PageFindings(page_title="Example", answer="Saw the page.")

    async def fake_run_once(url, goal):
        llms_used.append(type(tools._llm()))
        return FakeHistory(done=len(llms_used) > 1)

    monkeypatch.setattr(tools, "_run_once", fake_run_once)
    result = json.loads(await tools.abrowse_page("https://example.com", "what is on it"))

    assert llms_used == [ChatBrowserUse, ChatOpenRouter], "must retry on the provider model"
    assert result["completed"] is True
    assert result["llm"] == "openai/gpt-5.4-mini" or "browser-use" not in result["llm"]
    # The hosted model is skipped from now on rather than rejected again.
    assert tools._hosted_llm_unusable is True
    assert isinstance(tools._llm(), ChatOpenRouter)


def test_model_quota_is_distinguished_from_a_blocked_page():
    assert _model_quota_exhausted(["Error code: 402 - Prompt tokens limit exceeded: 8559 > 6222"])
    assert not _model_quota_exhausted(["login wall detected", "captcha"])


async def test_out_of_credit_reports_billing_not_a_blocked_page(settings, monkeypatch):
    """The page was reachable; only the model ran dry. Never report that as blocked."""
    monkeypatch.setattr(web_scout, "browser_available", lambda: True)
    tools = WebScoutTools(settings)

    class QuotaHistory:
        def is_done(self): return False
        def errors(self): return ["Error code: 402 - Prompt tokens limit exceeded: 8559 > 6222"]
        def urls(self): return ["https://later.com/"]
        def number_of_steps(self): return 4
        structured_output = None
        def final_result(self): return None

    async def fake_run_once(url, goal):
        return QuotaHistory()

    monkeypatch.setattr(tools, "_run_once", fake_run_once)
    result = json.loads(await tools.abrowse_page("https://later.com", "what is on it"))

    assert result["error"] is True
    assert result["code"] == "model_quota"
    assert "blocked" not in result
    assert result["final_url"] == "https://later.com/"
    assert "credit" in result["hint"].lower()


def test_scout_is_told_to_always_use_its_browser(settings, workspace, zernio_client, tmp_path):
    """The scout refusing to browse is the bug this guards; it owns a browser."""
    db = SqliteDb(db_file=str(tmp_path / "agno.db"))
    model = OpenAIChat(id="gpt-test", api_key="sk-test")
    on = build_team(replace(settings, browser_scout="on"), db, workspace, zernio=zernio_client, model=model)

    said = " ".join(on.web_scout.instructions)
    assert "Always answer a page request by calling browse_page" in said
    assert "never reply that you are unable to browse" in said


def test_browser_agent_uses_gemini_when_the_provider_is_google(settings):
    """The Web Scout must follow MODEL_PROVIDER, not stay on a different provider."""
    from browser_use.llm.google.chat import ChatGoogle

    tools = WebScoutTools(
        replace(settings, model_provider="google", google_api_key="AIza-test", browser_model_id="gemini-2.5-flash")
    )

    llm = tools._llm()
    assert isinstance(llm, ChatGoogle)
    assert llm.model == "gemini-2.5-flash"

    # And it is still the fallback when the hosted browser-use model is in front.
    hosted = WebScoutTools(
        replace(settings, model_provider="google", google_api_key="AIza-test", browser_use_api_key="bu_test")
    )
    assert isinstance(hosted._fallback_llm(), ChatGoogle)
