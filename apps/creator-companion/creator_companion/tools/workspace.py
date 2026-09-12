"""Local workspace: what the team produces and what a person still needs to act on.

Stored in SQLite next to the Agno session database. Nothing here touches a social
platform; it is the queue of attention items, reply drafts, content ideas, and
reports that survive a restart and can be read back through the HTTP API.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from agno.tools import Toolkit

SCHEMA = """
CREATE TABLE IF NOT EXISTS attention_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  priority TEXT NOT NULL,
  category TEXT NOT NULL,
  platform TEXT,
  account_id TEXT,
  post_id TEXT,
  comment_id TEXT,
  author TEXT,
  summary TEXT NOT NULL,
  suggested_action TEXT,
  resolution TEXT
);
CREATE TABLE IF NOT EXISTS reply_drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  platform TEXT NOT NULL,
  account_id TEXT NOT NULL,
  post_id TEXT NOT NULL,
  comment_id TEXT,
  author TEXT,
  comment_text TEXT,
  draft TEXT NOT NULL,
  rationale TEXT
);
CREATE TABLE IF NOT EXISTS content_ideas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed',
  title TEXT NOT NULL,
  hook TEXT NOT NULL,
  format TEXT NOT NULL,
  platform TEXT NOT NULL,
  rationale TEXT NOT NULL,
  experiment TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  title TEXT NOT NULL,
  markdown TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_events (
  event_id TEXT PRIMARY KEY,
  event TEXT NOT NULL,
  received_at TEXT NOT NULL
);
"""

PRIORITIES = ("high", "medium", "low")
CATEGORIES = ("question", "complaint", "collaboration", "praise", "spam", "theme", "performance", "other")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Workspace:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _insert(self, table: str, values: dict[str, Any]) -> int:
        values = {"created_at": _now(), **values}
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with self._connect() as conn:
            cur = conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))
            return int(cur.lastrowid)

    def _select(self, table: str, where: str = "", args: Sequence[Any] = (), limit: int = 50) -> list[dict]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, (*args, limit))]

    # attention -------------------------------------------------------------

    def add_attention_item(self, **values: Any) -> int:
        return self._insert("attention_items", values)

    def list_attention_items(self, status: Optional[str] = "open", limit: int = 50) -> list[dict]:
        if status:
            return self._select("attention_items", "status = ?", (status,), limit)
        return self._select("attention_items", limit=limit)

    def resolve_attention_item(self, item_id: int, resolution: Optional[str]) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE attention_items SET status = 'resolved', resolution = ? WHERE id = ? AND status = 'open'",
                (resolution, item_id),
            )
            return cur.rowcount == 1

    # drafts ----------------------------------------------------------------

    def add_reply_draft(self, **values: Any) -> int:
        return self._insert("reply_drafts", values)

    def list_reply_drafts(self, status: Optional[str] = "pending", limit: int = 50) -> list[dict]:
        if status:
            return self._select("reply_drafts", "status = ?", (status,), limit)
        return self._select("reply_drafts", limit=limit)

    def set_reply_draft_status(self, draft_id: int, status: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE reply_drafts SET status = ? WHERE id = ?", (status, draft_id))
            return cur.rowcount == 1

    # ideas -----------------------------------------------------------------

    def add_content_idea(self, **values: Any) -> int:
        return self._insert("content_ideas", values)

    def list_content_ideas(self, limit: int = 50) -> list[dict]:
        return self._select("content_ideas", limit=limit)

    # reports ---------------------------------------------------------------

    def add_report(self, title: str, markdown: str) -> int:
        return self._insert("reports", {"title": title, "markdown": markdown})

    def list_reports(self, limit: int = 20) -> list[dict]:
        return self._select("reports", limit=limit)

    def latest_report(self) -> Optional[dict]:
        rows = self._select("reports", limit=1)
        return rows[0] if rows else None

    # webhooks --------------------------------------------------------------

    def record_webhook_event(self, event_id: str, event: str) -> bool:
        """Return True the first time an event id is seen, False on a redelivery."""
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO webhook_events (event_id, event, received_at) VALUES (?, ?, ?)",
                    (event_id, event, _now()),
                )
            except sqlite3.IntegrityError:
                return False
            return True


ATTENTION_TOOLS = ("flag_for_attention", "list_attention_items", "resolve_attention_item")
DRAFT_TOOLS = ("save_reply_draft", "list_reply_drafts")
IDEA_TOOLS = ("save_content_idea", "list_content_ideas")
REPORT_TOOLS = ("save_report", "get_latest_report", "list_attention_items", "list_reply_drafts", "list_content_ideas")


class WorkspaceTools(Toolkit):
    def __init__(self, workspace: Workspace, include_tools: Optional[Sequence[str]] = None, **kwargs) -> None:
        self.workspace = workspace
        super().__init__(
            name="workspace",
            tools=[
                self.flag_for_attention,
                self.list_attention_items,
                self.resolve_attention_item,
                self.save_reply_draft,
                self.list_reply_drafts,
                self.save_content_idea,
                self.list_content_ideas,
                self.save_report,
                self.get_latest_report,
            ],
            include_tools=list(include_tools) if include_tools else None,
            **kwargs,
        )

    def flag_for_attention(
        self,
        summary: str,
        category: str,
        priority: str,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        post_id: Optional[str] = None,
        comment_id: Optional[str] = None,
        author: Optional[str] = None,
        suggested_action: Optional[str] = None,
    ) -> str:
        """Record something the creator should look at (a question, complaint, collab offer, or trend).

        Args:
            summary: One or two sentences the creator can act on without opening the platform.
            category: One of question, complaint, collaboration, praise, spam, theme, performance, other.
            priority: high, medium, or low.
            platform: Platform slug the item came from.
            account_id: Connected account id.
            post_id: Post the item relates to.
            comment_id: Comment id when the item is a specific comment.
            author: Username or display name of the person involved.
            suggested_action: What you recommend the creator does next.
        """
        category = category.lower().strip()
        priority = priority.lower().strip()
        if category not in CATEGORIES:
            return json.dumps({"error": True, "message": f"category must be one of {CATEGORIES}"})
        if priority not in PRIORITIES:
            return json.dumps({"error": True, "message": f"priority must be one of {PRIORITIES}"})
        item_id = self.workspace.add_attention_item(
            summary=summary,
            category=category,
            priority=priority,
            platform=platform,
            account_id=account_id,
            post_id=post_id,
            comment_id=comment_id,
            author=author,
            suggested_action=suggested_action,
        )
        return json.dumps({"ok": True, "attention_item_id": item_id})

    def list_attention_items(self, status: str = "open", limit: int = 20) -> str:
        """List recorded attention items.

        Args:
            status: "open", "resolved", or "all".
            limit: Maximum items to return.
        """
        items = self.workspace.list_attention_items(None if status == "all" else status, limit)
        return json.dumps({"count": len(items), "items": items}, default=str)

    def resolve_attention_item(self, item_id: int, resolution: Optional[str] = None) -> str:
        """Mark an attention item as handled.

        Args:
            item_id: The attention_item_id returned by flag_for_attention.
            resolution: What was done about it.
        """
        ok = self.workspace.resolve_attention_item(item_id, resolution)
        return json.dumps({"ok": ok, "attention_item_id": item_id})

    def save_reply_draft(
        self,
        draft: str,
        platform: str,
        account_id: str,
        post_id: str,
        comment_id: Optional[str] = None,
        author: Optional[str] = None,
        comment_text: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> str:
        """Save a suggested reply for the creator to review. This does not post anything.

        Args:
            draft: The reply text, ready to send.
            platform: Platform slug of the comment.
            account_id: Connected account id that would send the reply.
            post_id: Post the comment is on (use the id get_post_comments accepted).
            comment_id: The comment being replied to.
            author: Username of the commenter.
            comment_text: The original comment, for context.
            rationale: Why this reply, in one sentence.
        """
        draft_id = self.workspace.add_reply_draft(
            draft=draft,
            platform=platform,
            account_id=account_id,
            post_id=post_id,
            comment_id=comment_id,
            author=author,
            comment_text=comment_text,
            rationale=rationale,
        )
        return json.dumps({"ok": True, "reply_draft_id": draft_id, "status": "pending"})

    def list_reply_drafts(self, status: str = "pending", limit: int = 20) -> str:
        """List saved reply drafts.

        Args:
            status: "pending", "sent", "dismissed", or "all".
            limit: Maximum drafts to return.
        """
        drafts = self.workspace.list_reply_drafts(None if status == "all" else status, limit)
        return json.dumps({"count": len(drafts), "drafts": drafts}, default=str)

    def save_content_idea(
        self,
        title: str,
        hook: str,
        format: str,
        platform: str,
        rationale: str,
        experiment: Optional[str] = None,
    ) -> str:
        """Save a concrete next-content idea grounded in the monitoring findings.

        Args:
            title: Working title.
            hook: The first line or opening seconds, written out.
            format: e.g. "reel", "carousel", "short", "thread", "long-form video".
            platform: Platform slug this idea targets.
            rationale: Which finding (post, comment theme, metric) motivates it.
            experiment: Optional A/B or measurement plan, e.g. "post at 18:00 UTC vs 09:00 UTC, compare 48h views".
        """
        idea_id = self.workspace.add_content_idea(
            title=title, hook=hook, format=format, platform=platform, rationale=rationale, experiment=experiment
        )
        return json.dumps({"ok": True, "content_idea_id": idea_id})

    def list_content_ideas(self, limit: int = 20) -> str:
        """List saved content ideas, newest first.

        Args:
            limit: Maximum ideas to return.
        """
        ideas = self.workspace.list_content_ideas(limit)
        return json.dumps({"count": len(ideas), "ideas": ideas}, default=str)

    def save_report(self, title: str, markdown: str) -> str:
        """Persist the finished monitoring report so it can be read back later.

        Args:
            title: Report title, e.g. "Daily creator report 2026-09-12".
            markdown: The full report in Markdown.
        """
        report_id = self.workspace.add_report(title, markdown)
        return json.dumps({"ok": True, "report_id": report_id})

    def get_latest_report(self) -> str:
        """Read the most recent saved report, to compare against or continue from."""
        report = self.workspace.latest_report()
        return json.dumps(report or {"report": None, "note": "No report saved yet."}, default=str)
