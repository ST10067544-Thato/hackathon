"""The Creator Companion team: Social Monitor, Community Advisor, Content Strategist.

Each member gets only the tools its role needs. Writes to the creator's accounts
(``reply_to_comment``, ``create_post_draft``) pause for approval; drafts, attention
items, ideas, and reports go to the local workspace instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agno.agent import Agent
from agno.db.base import BaseDb
from agno.models.base import Model
from agno.models.google import Gemini
from agno.models.openai import OpenAIChat
from agno.models.openrouter import OpenRouter
from agno.team import Team
from agno.tools.exa import ExaTools

from creator_companion.config import Settings
from creator_companion.tools.web_scout import WebScoutTools, browser_available
from creator_companion.tools.workspace import (
    ATTENTION_TOOLS,
    DRAFT_TOOLS,
    IDEA_TOOLS,
    REPORT_TOOLS,
    Workspace,
    WorkspaceTools,
)
from creator_companion.tools.zernio_tools import (
    COMMUNITY_TOOLS,
    MONITOR_TOOLS,
    STRATEGIST_TOOLS,
    ZernioTools,
)
from creator_companion.zernio import ZernioClient

TEAM_ID = "creator-companion"
MONITOR_ID = "social-monitor"
COMMUNITY_ID = "community-advisor"
STRATEGIST_ID = "content-strategist"
WEB_SCOUT_ID = "web-scout"


def build_model(settings: Settings) -> Model:
    if settings.model_provider == "openrouter":
        return OpenRouter(id=settings.model_id, api_key=settings.openrouter_api_key)
    if settings.model_provider == "google":
        return Gemini(id=settings.model_id, api_key=settings.google_api_key)
    return OpenAIChat(id=settings.model_id, api_key=settings.openai_api_key)


@dataclass
class CreatorCompanion:
    team: Team
    monitor: Agent
    community: Agent
    strategist: Agent
    web_scout: Optional[Agent]
    workspace: Workspace
    zernio: ZernioClient

    @property
    def members(self) -> list[Agent]:
        return [m for m in (self.monitor, self.community, self.strategist, self.web_scout) if m is not None]


def build_team(
    settings: Settings,
    db: BaseDb,
    workspace: Workspace,
    zernio: Optional[ZernioClient] = None,
    model: Optional[Model] = None,
) -> CreatorCompanion:
    zernio = zernio or ZernioClient(settings.zernio_api_key, settings.zernio_base_url)
    model = model or build_model(settings)
    profile_id = settings.zernio_profile_id

    monitor = Agent(
        id=MONITOR_ID,
        name="Social Monitor",
        role="Retrieve connected-account posts, comments, and analytics.",
        model=model,
        db=db,
        tools=[ZernioTools(zernio, include_tools=MONITOR_TOOLS, default_profile_id=profile_id)],
        instructions=[
            "Retrieve only the social data needed for the requested review.",
            "Summarize post performance, meaningful changes, and notable comments.",
            "Start with list_accounts, then use small limits and a date range; do not page through everything.",
            "Report numbers exactly as returned, with the platform and post they belong to; say when metrics are pending or unavailable.",
            "When a call returns an error, include what failed and the hint in your summary instead of retrying repeatedly.",
        ],
        add_datetime_to_context=True,
        markdown=True,
    )

    community = Agent(
        id=COMMUNITY_ID,
        name="Community Advisor",
        role="Find comments that need attention and identify audience themes.",
        model=model,
        db=db,
        tools=[
            ZernioTools(zernio, include_tools=COMMUNITY_TOOLS, default_profile_id=profile_id),
            WorkspaceTools(workspace, include_tools=ATTENTION_TOOLS + DRAFT_TOOLS),
        ],
        instructions=[
            "Prioritize questions, complaints, collaboration opportunities, and recurring themes.",
            "Draft response suggestions, but do not post or reply unless explicitly authorized.",
            "Record each item worth the creator's time with flag_for_attention, and save suggested replies with save_reply_draft.",
            "reply_to_comment publishes publicly and pauses for the creator's approval; only call it when the creator explicitly asked you to reply, and pass the exact draft text.",
            "Quote the commenter's words when summarizing so the creator can recognize the comment.",
        ],
        add_datetime_to_context=True,
        markdown=True,
    )

    strategist_tools: list = [
        ZernioTools(zernio, include_tools=STRATEGIST_TOOLS, default_profile_id=profile_id),
        WorkspaceTools(workspace, include_tools=IDEA_TOOLS),
    ]
    if settings.exa_api_key:
        strategist_tools.append(
            ExaTools(
                api_key=settings.exa_api_key,
                enable_find_similar=False,
                enable_answer=False,
                num_results=5,
                text_length_limit=800,
            )
        )

    strategist = Agent(
        id=STRATEGIST_ID,
        name="Content Strategist",
        role="Convert performance and audience signals into content advice.",
        model=model,
        db=db,
        tools=strategist_tools,
        instructions=[
            "Recommend concrete next content ideas, hooks, and experiments.",
            "Ground recommendations in the monitoring findings.",
            "Save each recommendation with save_content_idea, naming the post, metric, or comment theme that motivates it.",
            "Use get_best_times_to_post and get_post_timeline to back timing and format advice with data.",
            "If web search is available, use it only to check formats or topics trending in the creator's niche, and cite the source.",
            "create_post_draft saves a Zernio draft and pauses for approval; use it only when the creator asks for a draft in their account.",
        ],
        add_datetime_to_context=True,
        markdown=True,
    )

    web_scout = build_web_scout(settings, model, db)

    members = [monitor, community, strategist] + ([web_scout] if web_scout else [])

    # Only promise the browser when the member actually exists. Without this the
    # leader either offers a teammate it cannot reach, or — having no browsing
    # instruction at all — answers "I cannot navigate to external websites" while
    # Web Scout is sitting right there in the roster.
    if web_scout:
        browsing_instructions = [
            "You CAN read public web pages: delegate to Web Scout. Never tell the creator you are unable to visit a website or fetch live information while Web Scout is a member.",
            "Use Web Scout for anything outside the connected accounts: a competitor's or peer's public profile, a link the creator shares, a hashtag or trend page, a post linked in a comment, a product or pricing page.",
            "When the creator names a site, brand, or handle instead of a URL (for example \"the Later website\" or \"@nasa on instagram\"), resolve it to the obvious public URL yourself (https://later.com, https://www.instagram.com/nasa/) and delegate with that URL. Only ask the creator for a URL when the name is genuinely ambiguous, and say which guess you would otherwise use.",
            "Give Web Scout the exact URL and one specific goal. It is read-only and slow, so ask for one page at a time.",
            "Report Web Scout's findings with the URL it actually landed on; if it reports blocked=true, say the page was blocked rather than guessing at its contents.",
        ]
    else:
        browsing_instructions = [
            "You have no browser in this deployment: you cannot open web pages, and the only live data you can reach is the connected accounts through Social Monitor and Community Advisor. Say so plainly if asked to visit a site.",
        ]
    team = Team(
        id=TEAM_ID,
        name="Creator Companion",
        description="Monitors a creator's connected social accounts and turns comments and analytics into a report, reply drafts, and next content ideas.",
        model=model,
        db=db,
        members=members,
        tools=[WorkspaceTools(workspace, include_tools=REPORT_TOOLS)],
        instructions=[
            "Coordinate a monitoring report for the creator.",
            "Lead with items that need attention, then performance insights and next actions.",
            "Keep recommendations specific and actionable.",
            "Delegate data retrieval to Social Monitor, comment triage and reply drafts to Community Advisor, and content advice to Content Strategist; pass each member the account ids and time window they need.",
            "Answer the request that was actually made. A request to look something up on the web is not a request for a monitoring report: do that lookup and answer it, and do not redirect the creator back to a report they did not ask for.",
            *browsing_instructions,
            "When the request is for a monitoring report, finish by calling save_report with the complete report so it survives a restart, then return the same report. Do not save a report for one-off questions or single-comment triage.",
            "Never claim a reply was posted or a draft was created unless the tool result confirms it; approval-gated tools may still be waiting on the creator.",
        ],
        add_history_to_context=True,
        num_history_runs=5,
        add_datetime_to_context=True,
        show_members_responses=True,
        markdown=True,
    )

    return CreatorCompanion(
        team=team,
        monitor=monitor,
        community=community,
        strategist=strategist,
        web_scout=web_scout,
        workspace=workspace,
        zernio=zernio,
    )


def web_scout_enabled(settings: Settings) -> bool:
    if settings.browser_scout == "off":
        return False
    if settings.browser_scout == "on":
        return True
    return browser_available()


def build_web_scout(settings: Settings, model: Model, db: BaseDb) -> Optional[Agent]:
    """The browser-use member. Absent unless the `browser` extra is installed (or BROWSER_SCOUT=on)."""
    if not web_scout_enabled(settings):
        return None
    return Agent(
        id=WEB_SCOUT_ID,
        name="Web Scout",
        role="Read public web pages the social APIs cannot see, in a real browser.",
        model=model,
        db=db,
        tools=[
            WebScoutTools(
                settings,
                max_steps=settings.browser_max_steps,
                timeout_seconds=settings.browser_timeout_seconds,
                headless=settings.browser_headless,
            )
        ],
        instructions=[
            "You have a real browser. Always answer a page request by calling browse_page — never reply that you are unable to browse, visit a site, or read a page, and never ask the requester to paste the page contents for you.",
            "If you were given a site or brand name rather than a URL, use the obvious public URL for it and say which one you opened.",
            "Browse only public pages you were given a URL for, or that the goal clearly names; never log in, and never click anything that posts, likes, follows, subscribes, or buys.",
            "Call browse_page once per page with a specific goal; report only what the tool says was on the page, with the URL.",
            "If the page was blocked (login wall, captcha, error) say so plainly instead of guessing.",
            "Turn observations into signals a creator can use: formats, hooks, posting cadence, offers, engagement numbers as displayed.",
        ],
        add_datetime_to_context=True,
        markdown=True,
    )
