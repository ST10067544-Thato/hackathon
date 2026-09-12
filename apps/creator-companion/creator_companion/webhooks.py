"""HTTP surface mounted alongside AgentOS.

* ``POST /webhooks/zernio`` receives Zernio events. Deliveries are verified with the
  ``X-Zernio-Signature`` HMAC (https://docs.zernio.com/webhooks#signatures), deduped
  by event id, and ``comment.received`` events are handed to the team in the
  background so the creator gets a triage without polling.
* ``GET /workspace/...`` reads back what the team produced, for a web UI or a
  browser agent.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request

from creator_companion.agents import CreatorCompanion
from creator_companion.config import Settings

log = logging.getLogger("creator_companion.webhooks")

SIGNATURE_HEADERS = ("X-Zernio-Signature", "X-Late-Signature")


def verify_signature(raw_body: bytes, secret: str, signature: Optional[str]) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def comment_triage_prompt(payload: dict[str, Any]) -> str:
    comment = payload.get("comment") or {}
    post = payload.get("post") or {}
    account = payload.get("account") or {}
    author = comment.get("author") or {}
    who = author.get("username") or author.get("name") or author.get("id") or "unknown"
    post_text = (post.get("content") or "").strip()
    if len(post_text) > 400:
        post_text = post_text[:400] + "…"
    return (
        "A new comment just arrived via webhook. Triage it for the creator.\n\n"
        f"Platform: {comment.get('platform') or account.get('platform')}\n"
        f"Account: @{account.get('username')} (accountId {account.get('accountId') or account.get('id')})\n"
        f"Post: platformPostId {comment.get('platformPostId') or post.get('platformPostId')}"
        f"{' / zernio post ' + str(post.get('id')) if post.get('id') else ''}"
        f"{' / ' + post['permalink'] if post.get('permalink') else ''}\n"
        f"Post text: {post_text or '(not synced)'}\n"
        f"Comment id: {comment.get('id')}{' (reply to ' + str(comment.get('parentCommentId')) + ')' if comment.get('isReply') else ''}\n"
        f"From: {who}\n"
        f"Comment: {json.dumps(comment.get('text') or '')}\n\n"
        "Decide whether it needs the creator's attention (question, complaint, collaboration, praise, spam). "
        "If it does, flag it with flag_for_attention and save a suggested reply with save_reply_draft. "
        "Do not call reply_to_comment: the creator has not authorized a reply. "
        "Answer in three lines or fewer."
    )


async def triage_comment(companion: CreatorCompanion, payload: dict[str, Any]) -> None:
    account = payload.get("account") or {}
    session_id = f"webhook-{account.get('accountId') or account.get('id') or 'unknown'}"
    try:
        await companion.team.arun(comment_triage_prompt(payload), session_id=session_id)
    except Exception:  # noqa: BLE001 - background task; never raise into the server loop
        log.exception("comment triage failed for event %s", payload.get("id"))


def create_base_app(companion: CreatorCompanion, settings: Settings) -> FastAPI:
    app = FastAPI(title="Creator Companion", version="0.1.0")
    workspace = companion.workspace

    @app.post("/webhooks/zernio", status_code=202)
    async def zernio_webhook(request: Request, background: BackgroundTasks) -> dict[str, Any]:
        raw = await request.body()
        if not settings.zernio_webhook_secret:
            raise HTTPException(status_code=503, detail="ZERNIO_WEBHOOK_SECRET is not configured")
        signature = next((request.headers.get(h) for h in SIGNATURE_HEADERS if request.headers.get(h)), None)
        if not verify_signature(raw, settings.zernio_webhook_secret, signature):
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        try:
            payload = json.loads(raw or b"{}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="body is not JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")

        event = str(payload.get("event") or request.headers.get("X-Zernio-Event") or "")
        event_id = str(payload.get("id") or request.headers.get("X-Zernio-Event-Id") or "")
        if event == "webhook.test":
            return {"ok": True, "event": event}
        if event_id and not workspace.record_webhook_event(event_id, event):
            return {"ok": True, "event": event, "duplicate": True}
        if event == "comment.received":
            background.add_task(triage_comment, companion, payload)
            return {"ok": True, "event": event, "queued": True}
        return {"ok": True, "event": event, "ignored": True}

    @app.get("/workspace/attention")
    def list_attention(status: str = Query("open"), limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        items = workspace.list_attention_items(None if status == "all" else status, limit)
        return {"count": len(items), "items": items}

    @app.get("/workspace/drafts")
    def list_drafts(status: str = Query("pending"), limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        drafts = workspace.list_reply_drafts(None if status == "all" else status, limit)
        return {"count": len(drafts), "drafts": drafts}

    @app.post("/workspace/drafts/{draft_id}/status")
    def set_draft_status(draft_id: int, status: str = Query(..., pattern="^(pending|sent|dismissed)$")) -> dict[str, Any]:
        if not workspace.set_reply_draft_status(draft_id, status):
            raise HTTPException(status_code=404, detail="draft not found")
        return {"ok": True, "draft_id": draft_id, "status": status}

    @app.get("/workspace/ideas")
    def list_ideas(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        ideas = workspace.list_content_ideas(limit)
        return {"count": len(ideas), "ideas": ideas}

    @app.get("/workspace/reports")
    def list_reports(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        reports = workspace.list_reports(limit)
        return {"count": len(reports), "reports": reports}

    @app.get("/workspace/reports/latest")
    def latest_report() -> dict[str, Any]:
        report = workspace.latest_report()
        if not report:
            raise HTTPException(status_code=404, detail="no report saved yet")
        return report

    return app
