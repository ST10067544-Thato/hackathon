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
from agno.models.openai import OpenAIChat
from agno.models.openrouter import OpenRouter
from agno.team import Team
from agno.tools.exa import ExaTools

from creator_companion.config import Settings
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


def build_model(settings: Settings) -> Model:
    if settings.model_provider == "openrouter":
        return OpenRouter(id=settings.model_id, api_key=settings.openrouter_api_key)
    return OpenAIChat(id=settings.model_id, api_key=settings.openai_api_key)


@dataclass
class CreatorCompanion:
    team: Team
    monitor: Agent
    community: Agent
    strategist: Agent
    workspace: Workspace
    zernio: ZernioClient


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

    team = Team(
        id=TEAM_ID,
        name="Creator Companion",
        description="Monitors a creator's connected social accounts and turns comments and analytics into a report, reply drafts, and next content ideas.",
        model=model,
        db=db,
        members=[monitor, community, strategist],
        tools=[WorkspaceTools(workspace, include_tools=REPORT_TOOLS)],
        instructions=[
            "Coordinate a monitoring report for the creator.",
            "Lead with items that need attention, then performance insights and next actions.",
            "Keep recommendations specific and actionable.",
            "Delegate data retrieval to Social Monitor, comment triage and reply drafts to Community Advisor, and content advice to Content Strategist; pass each member the account ids and time window they need.",
            "Finish by calling save_report with the complete report so it survives a restart, then return the same report.",
            "Never claim a reply was posted or a draft was created unless the tool result confirms it; approval-gated tools may still be waiting on the creator.",
        ],
        add_history_to_context=True,
        num_history_runs=5,
        add_datetime_to_context=True,
        show_members_responses=True,
        markdown=True,
    )

    return CreatorCompanion(team=team, monitor=monitor, community=community, strategist=strategist, workspace=workspace, zernio=zernio)
