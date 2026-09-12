"""Agno toolkit over the Zernio API.

Endpoint paths, parameters, and body fields come from https://docs.zernio.com — do
not add a tool here without checking the reference page for that endpoint.

Read tools return Zernio's JSON as a string. The two write tools (``reply_to_comment``
and ``create_post_draft``) are registered with ``requires_confirmation`` so an agent
run pauses at the write boundary until a person approves it in AgentOS.
"""

from __future__ import annotations

from typing import Optional, Sequence

from agno.tools import Toolkit

from creator_companion.zernio import ZernioClient, ZernioError, tool_result

READ_TOOLS = (
    "list_accounts",
    "list_posts",
    "list_platform_posts",
    "get_post_analytics",
    "get_post_timeline",
    "get_follower_stats",
    "list_commented_posts",
    "get_post_comments",
    "get_best_times_to_post",
)
WRITE_TOOLS = ("reply_to_comment", "create_post_draft")

MONITOR_TOOLS = (
    "list_accounts",
    "list_posts",
    "list_platform_posts",
    "get_post_analytics",
    "get_post_timeline",
    "get_follower_stats",
    "list_commented_posts",
    "get_post_comments",
)
COMMUNITY_TOOLS = ("list_accounts", "list_commented_posts", "get_post_comments", "reply_to_comment")
STRATEGIST_TOOLS = (
    "list_accounts",
    "get_post_analytics",
    "get_post_timeline",
    "get_best_times_to_post",
    "get_follower_stats",
    "create_post_draft",
)

INSTRUCTIONS = """\
Zernio tool guidance:
- Call list_accounts first when you need an accountId; most other calls need one.
- Comment and analytics reads are cached by Zernio for up to 10 minutes; do not poll.
- Analytics may return status "sync_pending" (HTTP 202); say so rather than inventing numbers.
- A result with "error": true explains what failed and a hint; surface it to the creator.
- reply_to_comment and create_post_draft write to the creator's accounts and pause for approval.
"""


class ZernioTools(Toolkit):
    def __init__(
        self,
        client: ZernioClient,
        include_tools: Optional[Sequence[str]] = None,
        default_profile_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.client = client
        self.default_profile_id = default_profile_id
        super().__init__(
            name="zernio",
            tools=[
                self.list_accounts,
                self.list_posts,
                self.list_platform_posts,
                self.get_post_analytics,
                self.get_post_timeline,
                self.get_follower_stats,
                self.list_commented_posts,
                self.get_post_comments,
                self.get_best_times_to_post,
                self.reply_to_comment,
                self.create_post_draft,
            ],
            include_tools=list(include_tools) if include_tools else None,
            requires_confirmation_tools=list(WRITE_TOOLS),
            instructions=INSTRUCTIONS,
            add_instructions=True,
            **kwargs,
        )

    # ---- accounts ---------------------------------------------------------

    def list_accounts(self, platform: Optional[str] = None, status: Optional[str] = None) -> str:
        """List the creator's connected social accounts and their ids.

        Args:
            platform: Filter by platform slug, e.g. "instagram", "tiktok", "youtube", "linkedin".
            status: "connected" for healthy accounts, "disconnected" for accounts needing reconnection.
        """
        return self._get(
            "/accounts",
            {"profileId": self.default_profile_id, "platform": platform, "status": status},
        )

    # ---- posts ------------------------------------------------------------

    def list_posts(
        self,
        limit: int = 20,
        source: str = "zernio",
        status: Optional[str] = None,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
    ) -> str:
        """List posts known to Zernio, newest first, with per-platform status and public URLs.

        Args:
            limit: Page size (keep small; 20 is plenty for a review).
            source: "zernio" for posts published through Zernio, "external" for posts synced from the platform.
            status: Post status filter, e.g. "published", "scheduled", "failed", "draft".
            platform: Platform slug filter.
            account_id: Only posts published via this connected account.
            date_from: YYYY-MM-DD lower bound.
            date_to: YYYY-MM-DD upper bound.
            search: Free-text search over post content.
            page: 1-based page number.
        """
        return self._get(
            "/posts",
            {
                "limit": limit,
                "source": source,
                "status": status,
                "platform": platform,
                "accountId": account_id,
                "profileId": self.default_profile_id,
                "dateFrom": date_from,
                "dateTo": date_to,
                "search": search,
                "page": page,
            },
        )

    def list_platform_posts(self, account_id: str) -> str:
        """Read the 25 most recent posts live from the platform for one account, including posts never made through Zernio.

        Args:
            account_id: Connected account id from list_accounts.
        """
        return self._get(f"/accounts/{account_id}/posts")

    # ---- analytics --------------------------------------------------------

    def get_post_analytics(
        self,
        post_id: Optional[str] = None,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        sort_by: str = "engagement",
        order: str = "desc",
        limit: int = 20,
        page: int = 1,
    ) -> str:
        """Get engagement metrics (likes, comments, shares, saves, impressions, reach, views) for posts.

        Without post_id returns a ranked page of posts with overview stats; with post_id returns one post.

        Args:
            post_id: Zernio post id or the platform's own post id for a single-post lookup.
            platform: Platform slug filter.
            account_id: Connected account id filter.
            from_date: YYYY-MM-DD inclusive lower bound (default 90 days ago, max range 366 days).
            to_date: YYYY-MM-DD inclusive upper bound (default today).
            sort_by: "date", "engagement", or a metric name such as "views" or "impressions".
            order: "desc" or "asc".
            limit: Page size.
            page: 1-based page number.
        """
        return self._get(
            "/analytics",
            {
                "postId": post_id,
                "platform": platform,
                "accountId": account_id,
                "profileId": self.default_profile_id,
                "fromDate": from_date,
                "toDate": to_date,
                "sortBy": sort_by,
                "order": order,
                "limit": limit,
                "page": page,
            },
        )

    def get_post_timeline(
        self, post_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None
    ) -> str:
        """Get a post's daily metrics over time, to see whether it is still growing or has decayed.

        Args:
            post_id: Zernio post id or the platform's own post id.
            from_date: ISO 8601 start (default 90 days ago).
            to_date: ISO 8601 end (default now).
        """
        return self._get("/analytics/post-timeline", {"postId": post_id, "fromDate": from_date, "toDate": to_date})

    def get_follower_stats(
        self,
        account_ids: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        granularity: Optional[str] = None,
    ) -> str:
        """Get follower count history and growth for connected accounts (refreshed daily by Zernio).

        Args:
            account_ids: Comma-separated account ids; omit for all accounts.
            from_date: YYYY-MM-DD (default 30 days ago).
            to_date: YYYY-MM-DD (default today).
            granularity: Aggregation level such as "day" or "week" when supported.
        """
        return self._get(
            "/accounts/follower-stats",
            {
                "accountIds": account_ids,
                "profileId": self.default_profile_id,
                "fromDate": from_date,
                "toDate": to_date,
                "granularity": granularity,
            },
        )

    def get_best_times_to_post(self, platform: Optional[str] = None, account_id: Optional[str] = None) -> str:
        """Get the best day/hour slots (UTC) to post, from historical engagement per slot.

        Args:
            platform: Platform slug; omit for all platforms.
            account_id: Connected account id; omit for all accounts.
        """
        return self._get(
            "/analytics/best-time",
            {"platform": platform, "accountId": account_id, "profileId": self.default_profile_id},
        )

    # ---- comments ---------------------------------------------------------

    def list_commented_posts(
        self,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        min_comments: Optional[int] = None,
        since: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> str:
        """List posts that have comments, with comment counts, across connected accounts.

        Args:
            platform: Platform slug; "facebook"/"instagram" return organic posts only.
            account_id: Connected account id filter.
            min_comments: Only posts with at least this many comments.
            since: Only posts created after this date (ISO 8601).
            limit: Page size.
            cursor: nextCursor from a previous page.
        """
        return self._get(
            "/inbox/comments",
            {
                "platform": platform,
                "accountId": account_id,
                "profileId": self.default_profile_id,
                "minComments": min_comments,
                "since": since,
                "limit": limit,
                "cursor": cursor,
            },
        )

    def get_post_comments(
        self,
        post_id: str,
        account_id: str,
        limit: int = 50,
        cursor: Optional[str] = None,
        comment_id: Optional[str] = None,
    ) -> str:
        """Read the comments on one post (text, author, timestamps, reply flags).

        Args:
            post_id: Zernio post id or the platform's own post id (platformPostId).
            account_id: The connected account that owns the post; required.
            limit: Maximum comments to return.
            cursor: pagination.cursor from a previous page; pass it back verbatim.
            comment_id: Reddit/TikTok only: fetch replies to this comment instead.
        """
        return self._get(
            f"/inbox/comments/{post_id}",
            {"accountId": account_id, "limit": limit, "cursor": cursor, "commentId": comment_id},
        )

    def reply_to_comment(
        self, post_id: str, account_id: str, message: str, comment_id: Optional[str] = None
    ) -> str:
        """Publish a reply on the creator's behalf. Pauses for the creator's approval before it runs.

        Args:
            post_id: Zernio post id or platform post id the comment is on.
            account_id: Connected account that will post the reply.
            message: The reply text exactly as it will appear publicly.
            comment_id: Reply to this specific comment; omit to comment on the post itself.
        """
        body = {"accountId": account_id, "message": message, "commentId": comment_id}
        try:
            return tool_result(self.client.post(f"/inbox/comments/{post_id}", body, idempotent=True))
        except ZernioError as exc:
            return exc.as_tool_result()

    # ---- drafts -----------------------------------------------------------

    def create_post_draft(
        self,
        content: str,
        title: Optional[str] = None,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> str:
        """Save a post idea as a Zernio draft (never publishes). Pauses for the creator's approval before it runs.

        Args:
            content: Full caption/text including any hashtags.
            title: Short internal label for the draft.
            platform: Target platform slug (needed together with account_id to attach a target).
            account_id: Connected account id for the target; drafts may omit both platform and account_id.
            rationale: One sentence on why this idea, stored in the draft metadata.
        """
        body: dict = {
            "content": content,
            "title": title,
            "isDraft": True,
            "metadata": {"source": "creator-companion", "rationale": rationale or ""},
        }
        if platform and account_id:
            body["platforms"] = [{"platform": platform, "accountId": account_id}]
        try:
            return tool_result(self.client.post("/posts", body))
        except ZernioError as exc:
            return exc.as_tool_result()

    # ---- helpers ----------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> str:
        try:
            return tool_result(self.client.get(path, params))
        except ZernioError as exc:
            return exc.as_tool_result()
