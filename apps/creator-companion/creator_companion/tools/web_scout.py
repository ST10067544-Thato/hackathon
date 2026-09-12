"""Web Scout: a browser-use agent wrapped as an Agno tool.

Adapted from the browser-use "check the visa appointment page" example: instead of
a fixed MFA URL and a "check this month, then next month" task, the tool takes any
public URL plus a goal, drives a real (headless) browser with vision, and returns
structured findings. It covers what the Zernio API cannot: a competitor's public
profile, the creator's link-in-bio page, a hashtag or explore page, a post someone
mentioned in a comment.

Guard rails: only http(s) URLs to public hosts, a step and time budget per run, and
a task prompt that forbids logging in or pressing anything that publishes, likes,
follows, or buys. The browser session is created per call and closed afterwards.

The local browser is pinned to Chromium (`channel="chromium"`), the build installed
by `browser-use install` — never the developer's own Google Chrome, which would
carry their real profile and logged-in sessions into a read-only scout.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from typing import Any, Optional
from urllib.parse import urlparse

from agno.tools import Toolkit
from pydantic import BaseModel, Field

from creator_companion.config import Settings
from creator_companion.zernio import tool_result

log = logging.getLogger("creator_companion.web_scout")

BLOCKED_HOSTS = {"localhost", "0.0.0.0", "broadcasthost"}


def browser_available() -> bool:
    """True when the optional `browser` extra is installed."""
    try:
        import browser_use  # noqa: F401
    except Exception:  # noqa: BLE001 - any import failure means "not available"
        return False
    return True


def validate_public_url(url: str) -> Optional[str]:
    """Return an error message when the URL is not a public http(s) address."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return "URL could not be parsed."
    if parsed.scheme not in ("http", "https"):
        return "Only http and https URLs can be browsed."
    host = (parsed.hostname or "").lower()
    if not host or host in BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        return "That host is not a public website."
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return None  # a DNS name; fine
    if not addr.is_global:
        return "Private or local IP addresses cannot be browsed."
    return None


class PageFindings(BaseModel):
    """What the browser agent must hand back (structured output for the run)."""

    page_title: str = Field(description="Title or main heading of the page you ended on.")
    answer: str = Field(description="Direct answer to the goal, in two to four sentences, based only on what was visible.")
    key_points: list[str] = Field(default_factory=list, description="Up to eight concrete observations (posts, captions, formats, pinned items, offers).")
    metrics: dict[str, str] = Field(default_factory=dict, description="Numbers seen on the page, e.g. followers, likes, views, prices, as displayed.")
    links: list[str] = Field(default_factory=list, description="Up to five URLs worth following up, as shown on the page.")
    blocked: bool = Field(default=False, description="True if a login wall, cookie wall, captcha, or error stopped you from seeing the content.")
    caveats: Optional[str] = Field(default=None, description="Anything that limits confidence in the answer.")


TASK_TEMPLATE = """\
Open {url} and stay on that site.

Goal: {goal}

Rules:
- Read only. Never log in, create an account, or enter personal data.
- Never click anything that posts, comments, likes, follows, subscribes, buys, or downloads.
- Dismiss cookie banners if they block the view; if a login wall, captcha, or error stops you, stop and report blocked=true.
- If the goal needs a second page on the same site (for example a profile's posts tab or the next page of results), you may open it; keep it to a few pages.
- Report only what you actually saw on screen. Quote captions and numbers as displayed.
When you are done, call done with the findings in the required structure.
"""


# Provider refused on billing/quota, not on anything about the page. Surfacing this
# as a distinct code stops the agent reporting "the page was blocked" when the real
# cause is an empty balance.
MODEL_QUOTA_MARKERS = (
    "prompt tokens limit exceeded",
    "requires more credits",
    "insufficient_quota",
    "exceeded your current quota",
    "rate limit",
    "error code: 402",
)


def _model_quota_exhausted(errors: list[str]) -> bool:
    blob = " ".join(errors).lower()
    return any(marker in blob for marker in MODEL_QUOTA_MARKERS)


GATEWAY_REJECTION_MARKERS = (
    "free tier",
    "llm gateway",
    "upgrade your subscription",
    "invalid api key",
    "unauthorized",
)


def _gateway_rejected(errors: list[str]) -> bool:
    """True when browser-use's hosted model refused the key rather than failing on the page.

    A free-tier BROWSER_USE_API_KEY is accepted for the browser but rejected by the
    LLM gateway, and browser-use's own `fallback_llm` does not always take over
    before `max_failures` ends the run. Detecting it lets us redo the run on the
    provider model instead of handing back an empty result.
    """
    blob = " ".join(errors).lower()
    return any(marker in blob for marker in GATEWAY_REJECTION_MARKERS)


class WebScoutTools(Toolkit):
    def __init__(
        self,
        settings: Settings,
        max_steps: int = 12,
        timeout_seconds: float = 180.0,
        headless: bool = True,
        **kwargs,
    ) -> None:
        self.settings = settings
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.headless = headless
        # Flipped the first time the hosted model refuses the key, so the rest of
        # the process goes straight to the provider model instead of paying for
        # the same rejection on every call.
        self._hosted_llm_unusable = False
        # Same tool under one name for both entrypoints: Agno's arun() uses the
        # async variant, run() the sync wrapper.
        super().__init__(
            name="web_scout",
            tools=[self.browse_page],
            async_tools=[(self.abrowse_page, "browse_page")],
            instructions=(
                "browse_page opens a real browser: use it only for public pages the creator or a teammate named, "
                "one page per call, with a specific goal. It takes up to a few minutes."
            ),
            add_instructions=True,
            **kwargs,
        )

    def browse_page(self, url: str, goal: str) -> str:
        """Open a public web page in a real browser and report what is there, in service of a goal.

        Use for things the social APIs cannot see: a competitor's or peer's public profile, the
        creator's link-in-bio or shop page, a hashtag, explore or trend page, or a post someone
        linked in a comment. Read-only; it never logs in or interacts with posts.

        Args:
            url: Full http(s) URL of a public page.
            goal: What to find out, specifically. e.g. "What formats and hooks are this account's last 6 posts using, and which got the most likes?"
        """
        return asyncio.run(self.abrowse_page(url, goal))

    async def abrowse_page(self, url: str, goal: str) -> str:
        """Open a public web page in a real browser and report what is there, in service of a goal.

        Use for things the social APIs cannot see: a competitor's or peer's public profile, the
        creator's link-in-bio or shop page, a hashtag, explore or trend page, or a post someone
        linked in a comment. Read-only; it never logs in or interacts with posts.

        Args:
            url: Full http(s) URL of a public page.
            goal: What to find out, specifically. e.g. "What formats and hooks are this account's last 6 posts using, and which got the most likes?"
        """
        problem = validate_public_url(url)
        if problem:
            return json.dumps({"error": True, "code": "invalid_url", "message": problem, "url": url})
        if not browser_available():
            return json.dumps(
                {
                    "error": True,
                    "code": "browser_not_installed",
                    "message": "The browser extra is not installed.",
                    "hint": "Run `uv sync --extra browser` in apps/creator-companion and restart the service.",
                }
            )
        try:
            return tool_result(await self._run(url.strip(), goal.strip()))
        except asyncio.TimeoutError:
            return json.dumps(
                {
                    "error": True,
                    "code": "timeout",
                    "message": f"The browser run exceeded {int(self.timeout_seconds)} seconds.",
                    "hint": "Narrow the goal or point at a more specific page.",
                    "url": url,
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface browser failures to the model, do not crash the run
            log.exception("browse_page failed for %s", url)
            return json.dumps(
                {"error": True, "code": "browser_error", "message": f"{type(exc).__name__}: {exc}", "url": url}
            )

    async def _run(self, url: str, goal: str) -> dict[str, Any]:
        history = await self._run_once(url, goal)

        # A hosted-model rejection is about the key, not the page: redo the run on
        # the provider model once, then remember so later calls skip the hosted one.
        errors = [e for e in history.errors() if e]
        if not history.is_done() and not self._hosted_llm_unusable and self._using_hosted_llm() and _gateway_rejected(errors):
            log.warning("browser-use hosted model rejected the key (%s); retrying on %s", errors[0][:120], self.settings.browser_model_id)
            self._hosted_llm_unusable = True
            history = await self._run_once(url, goal)

        findings: Any = history.structured_output
        if findings is None:
            final = history.final_result()
            findings = _parse_findings(final)
        elif isinstance(findings, BaseModel):
            findings = findings.model_dump()

        visited = [u for u in history.urls() if u]
        errors = [e for e in history.errors() if e]

        # The browser worked; the model behind it ran out of budget. Say exactly
        # that, so the agent reports a billing problem instead of claiming the
        # site blocked it.
        if not history.is_done() and _model_quota_exhausted(errors):
            return {
                "error": True,
                "code": "model_quota",
                "message": "The browsing model ran out of credit or hit its quota before finishing the page.",
                "hint": (
                    "Add credit for the browsing model, lower BROWSER_MAX_COMPLETION_TOKENS, "
                    "or point BROWSER_MODEL at a cheaper model. The page itself was reachable."
                ),
                "url": url,
                "final_url": visited[-1] if visited else url,
                "pages_visited": len(dict.fromkeys(visited)),
                "steps": history.number_of_steps(),
                "provider_error": errors[0][:400],
            }

        return {
            "url": url,
            "browser": "cloud" if (self.settings.browser_use_cloud and self.settings.browser_use_api_key) else "local chromium",
            "llm": ("browser-use → " if self._using_hosted_llm() else "") + self.settings.browser_model_id,
            "final_url": visited[-1] if visited else url,
            "pages_visited": len(dict.fromkeys(visited)),
            "steps": history.number_of_steps(),
            "completed": bool(history.is_done()),
            "findings": findings,
            "errors": errors[:5],
        }

    async def _run_once(self, url: str, goal: str):
        from browser_use import Agent, BrowserProfile

        agent = Agent(
            task=TASK_TEMPLATE.format(url=url, goal=goal),
            llm=self._llm(),
            fallback_llm=self._fallback_llm(),
            browser_profile=self._browser_profile(BrowserProfile),
            output_model_schema=PageFindings,
            # Screenshots dominate the prompt. Turning vision off is the cheapest
            # lever for an account on a tight token budget.
            use_vision=self.settings.browser_vision,
            max_failures=2,
            max_actions_per_step=3,
            calculate_cost=False,
        )
        return await asyncio.wait_for(agent.run(max_steps=self.max_steps), timeout=self.timeout_seconds)

    def _using_hosted_llm(self) -> bool:
        return bool(self.settings.browser_use_api_key) and not self._hosted_llm_unusable

    def _browser_profile(self, BrowserProfile):
        s = self.settings
        if s.browser_use_cloud and s.browser_use_api_key:
            # Hosted browser from Browser Use Cloud, billed to BROWSER_USE_API_KEY.
            return BrowserProfile(use_cloud=True, minimum_wait_page_load_time=0.5)
        # Pin the channel to Chromium (the Chrome-for-Testing build fetched by
        # `browser-use install`) rather than leaving it unset. Unset lets
        # browser-use pick whatever it finds — on a developer laptop that is
        # usually the installed Google Chrome, which carries the person's real
        # profile, cookies and logged-in sessions. A read-only scout must browse
        # as an anonymous visitor, and the demo must behave the same on every
        # machine, so the bundled Chromium is the only correct choice here.
        return BrowserProfile(
            channel="chromium",
            headless=self.headless,
            minimum_wait_page_load_time=0.5,
            window_size={"width": 1280, "height": 900},
        )

    def _llm(self):
        """Primary model: Browser Use's hosted `bu-latest` when its key is set, else the provider model."""
        if self._using_hosted_llm():
            # Tuned for browsing and billed to BROWSER_USE_API_KEY (paid plans only:
            # a free-tier key is rejected by the gateway, and the run then continues
            # on the fallback below).
            from browser_use.llm.browser_use.chat import ChatBrowserUse

            return ChatBrowserUse(api_key=self.settings.browser_use_api_key)
        return self._provider_llm()

    def _fallback_llm(self):
        """Used for the rest of a run after the primary model errors (rate limit, auth, plan)."""
        return self._provider_llm() if self._using_hosted_llm() else None

    def _provider_llm(self):
        s = self.settings
        if s.model_provider == "openrouter":
            from browser_use.llm.openrouter.chat import ChatOpenRouter

            return ChatOpenRouter(
                model=s.browser_model_id,
                api_key=s.openrouter_api_key,
                extra_body={"max_tokens": s.browser_max_completion_tokens},
            )
        if s.model_provider == "google":
            from browser_use.llm.google.chat import ChatGoogle

            # Gemini names the cap `max_output_tokens`; the rest of the browsing
            # budget (steps, timeout, vision) is unchanged across providers.
            return ChatGoogle(
                model=s.browser_model_id,
                api_key=s.google_api_key,
                config={"max_output_tokens": s.browser_max_completion_tokens},
            )
        from browser_use import ChatOpenAI

        return ChatOpenAI(
            model=s.browser_model_id, api_key=s.openai_api_key, max_completion_tokens=s.browser_max_completion_tokens
        )


def _parse_findings(final: Optional[str]) -> Any:
    if not final:
        return {"answer": "The browser run ended without a final report.", "blocked": True}
    try:
        parsed = json.loads(final)
    except (TypeError, ValueError):
        return {"answer": final}
    if isinstance(parsed, dict):
        try:
            return PageFindings.model_validate(parsed).model_dump()
        except Exception:  # noqa: BLE001 - keep whatever the model returned
            return parsed
    return {"answer": str(parsed)}
