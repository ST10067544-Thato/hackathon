import json

from creator_companion.tools.zernio_tools import WRITE_TOOLS, ZernioTools
from creator_companion.zernio import MAX_RESULT_CHARS, ZernioClient


def test_list_accounts_sends_bearer_and_drops_empty_params(fake_zernio, zernio_client):
    fake_zernio.respond("GET", "/api/v1/accounts", body={"accounts": [{"id": "acc1", "platform": "instagram"}]})
    tools = ZernioTools(zernio_client, default_profile_id="prof1")

    result = json.loads(tools.list_accounts(platform="instagram"))

    assert result["accounts"][0]["id"] == "acc1"
    req = fake_zernio.last
    assert req.headers["Authorization"] == "Bearer sk_test"
    assert dict(req.url.params) == {"profileId": "prof1", "platform": "instagram"}


def test_get_post_comments_uses_post_path_and_account_query(fake_zernio, zernio_client):
    fake_zernio.respond("GET", "/api/v1/inbox/comments/pp1", body={"comments": []})
    tools = ZernioTools(zernio_client)

    tools.get_post_comments(post_id="pp1", account_id="acc1", limit=10)

    assert dict(fake_zernio.last.url.params) == {"accountId": "acc1", "limit": "10"}


def test_reply_to_comment_posts_body_with_idempotency_key(fake_zernio, zernio_client):
    fake_zernio.respond("POST", "/api/v1/inbox/comments/pp1", body={"success": True, "data": {"commentId": "r1"}})
    tools = ZernioTools(zernio_client)

    result = json.loads(tools.reply_to_comment(post_id="pp1", account_id="acc1", message="Thanks!", comment_id="c1"))

    assert result["data"]["commentId"] == "r1"
    assert fake_zernio.last_json() == {"accountId": "acc1", "message": "Thanks!", "commentId": "c1"}
    assert len(fake_zernio.last.headers["Idempotency-Key"]) > 20


def test_create_post_draft_always_sets_is_draft(fake_zernio, zernio_client):
    fake_zernio.respond("POST", "/api/v1/posts", status=201, body={"post": {"id": "p1", "status": "draft"}})
    tools = ZernioTools(zernio_client)

    tools.create_post_draft(content="Behind the scenes", platform="instagram", account_id="acc1", rationale="asked a lot")

    body = fake_zernio.last_json()
    assert body["isDraft"] is True
    assert "publishNow" not in body and "scheduledFor" not in body
    assert body["platforms"] == [{"platform": "instagram", "accountId": "acc1"}]
    assert body["metadata"]["source"] == "creator-companion"


def test_write_tools_require_confirmation(zernio_client):
    tools = ZernioTools(zernio_client)
    for name in WRITE_TOOLS:
        assert tools.functions[name].requires_confirmation is True, name
    assert tools.functions["list_accounts"].requires_confirmation is not True


def test_include_tools_limits_registered_functions(zernio_client):
    tools = ZernioTools(zernio_client, include_tools=["list_accounts", "get_post_comments"])
    assert set(tools.functions) == {"list_accounts", "get_post_comments"}


def test_http_errors_become_structured_results(fake_zernio, zernio_client):
    fake_zernio.respond("GET", "/api/v1/analytics", status=403, body={"error": "Analytics add-on required", "code": "addon_required"})
    tools = ZernioTools(zernio_client)

    result = json.loads(tools.get_post_analytics(account_id="acc1"))

    assert result["error"] is True
    assert result["status"] == 403
    assert result["code"] == "addon_required"
    assert "add-on" in result["hint"]


def test_analytics_sync_pending_is_reported(fake_zernio, zernio_client):
    fake_zernio.respond("GET", "/api/v1/analytics", status=202, body={"message": "sync in progress"})
    tools = ZernioTools(zernio_client)

    result = json.loads(tools.get_post_analytics(post_id="p1"))

    assert result["status"] == "sync_pending"


def test_missing_api_key_reports_not_configured(fake_zernio):
    client = ZernioClient(None, base_url="https://zernio.test/api/v1", transport=fake_zernio.transport())
    tools = ZernioTools(client)

    result = json.loads(tools.list_accounts())

    assert result["code"] == "not_configured"
    assert fake_zernio.requests == []


def test_large_results_are_truncated_with_guidance(fake_zernio, zernio_client):
    fake_zernio.respond("GET", "/api/v1/posts", body={"posts": [{"content": "x" * 500} for _ in range(60)]})
    tools = ZernioTools(zernio_client)

    result = json.loads(tools.list_posts())

    assert result["truncated"] is True
    assert len(result["preview"]) == MAX_RESULT_CHARS
