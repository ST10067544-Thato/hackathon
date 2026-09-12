import hashlib
import hmac
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from creator_companion import webhooks
from creator_companion.webhooks import comment_triage_prompt, create_base_app, verify_signature

COMMENT_EVENT = {
    "id": "evt_1",
    "event": "comment.received",
    "comment": {
        "id": "c1",
        "postId": None,
        "platformPostId": "pp1",
        "platform": "instagram",
        "text": "Where can I buy this?",
        "author": {"id": "u1", "username": "sam"},
        "createdAt": "2026-09-12T10:00:00Z",
        "isReply": False,
        "parentCommentId": None,
    },
    "post": {"id": None, "platformPostId": "pp1", "content": "New drop", "imageUrl": None, "permalink": "https://instagram.com/p/x"},
    "account": {"id": "acc1", "accountId": "acc1", "platform": "instagram", "username": "creator"},
    "timestamp": "2026-09-12T10:00:01Z",
}


def sign(body: bytes, secret: str = "whsec_test") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post_event(client: TestClient, payload: dict, signature: str | None = None, header: str = "X-Zernio-Signature"):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    headers[header] = signature if signature is not None else sign(body)
    return client.post("/webhooks/zernio", content=body, headers=headers)


@pytest.fixture
def triaged(monkeypatch):
    calls: list[dict] = []

    async def fake_triage(companion, payload):
        calls.append(payload)

    monkeypatch.setattr(webhooks, "triage_comment", fake_triage)
    return calls


def test_verify_signature_is_constant_time_hex_hmac():
    body = b'{"event":"webhook.test"}'
    assert verify_signature(body, "s", sign(body, "s"))
    assert verify_signature(body, "s", sign(body, "s").upper())
    assert not verify_signature(body, "s", sign(body, "other"))
    assert not verify_signature(body, "s", None)


def test_comment_event_is_verified_deduped_and_queued(companion, settings, triaged):
    client = TestClient(create_base_app(companion, settings))

    first = post_event(client, COMMENT_EVENT)
    assert first.status_code == 202 and first.json()["queued"] is True

    again = post_event(client, COMMENT_EVENT)
    assert again.status_code == 202 and again.json()["duplicate"] is True

    assert [c["id"] for c in triaged] == ["evt_1"]


def test_legacy_signature_header_is_accepted(companion, settings, triaged):
    client = TestClient(create_base_app(companion, settings))
    assert post_event(client, COMMENT_EVENT, header="X-Late-Signature").status_code == 202


def test_bad_signature_and_missing_secret_are_rejected(companion, settings, triaged):
    client = TestClient(create_base_app(companion, settings))
    assert post_event(client, COMMENT_EVENT, signature="deadbeef").status_code == 401

    unconfigured = TestClient(create_base_app(companion, replace(settings, zernio_webhook_secret=None)))
    assert post_event(unconfigured, COMMENT_EVENT).status_code == 503
    assert triaged == []


def test_other_events_are_acknowledged_without_a_run(companion, settings, triaged):
    client = TestClient(create_base_app(companion, settings))
    assert post_event(client, {"event": "webhook.test"}).json() == {"ok": True, "event": "webhook.test"}
    assert post_event(client, {"id": "evt_9", "event": "post.published"}).json()["ignored"] is True
    assert triaged == []


def test_triage_prompt_carries_ids_and_forbids_replying():
    prompt = comment_triage_prompt(COMMENT_EVENT)
    assert "accountId acc1" in prompt
    assert "platformPostId pp1" in prompt
    assert "Comment id: c1" in prompt
    assert '"Where can I buy this?"' in prompt
    assert "Do not call reply_to_comment" in prompt


def test_workspace_endpoints_read_back_team_output(companion, settings):
    client = TestClient(create_base_app(companion, settings))
    ws = companion.workspace
    ws.add_attention_item(summary="s", category="question", priority="high")
    draft_id = ws.add_reply_draft(draft="d", platform="instagram", account_id="acc1", post_id="pp1")
    ws.add_report("Daily", "# hi")

    assert client.get("/workspace/attention").json()["count"] == 1
    assert client.get("/workspace/drafts").json()["count"] == 1
    assert client.post(f"/workspace/drafts/{draft_id}/status", params={"status": "sent"}).json()["status"] == "sent"
    assert client.get("/workspace/drafts").json()["count"] == 0
    assert client.post("/workspace/drafts/999/status", params={"status": "sent"}).status_code == 404
    assert client.get("/workspace/reports/latest").json()["title"] == "Daily"
