import json

from creator_companion.tools.workspace import Workspace, WorkspaceTools


def test_flag_for_attention_validates_and_persists(workspace: Workspace):
    tools = WorkspaceTools(workspace)

    bad = json.loads(tools.flag_for_attention(summary="?", category="rant", priority="high"))
    assert bad["error"] is True

    ok = json.loads(
        tools.flag_for_attention(
            summary="@sam asks where to buy the jacket",
            category="Question",
            priority="HIGH",
            platform="instagram",
            account_id="acc1",
            post_id="pp1",
            comment_id="c1",
            author="sam",
            suggested_action="Reply with the shop link",
        )
    )
    items = json.loads(tools.list_attention_items())
    assert items["count"] == 1
    assert items["items"][0]["id"] == ok["attention_item_id"]
    assert items["items"][0]["category"] == "question"
    assert items["items"][0]["priority"] == "high"

    assert json.loads(tools.resolve_attention_item(ok["attention_item_id"], "replied"))["ok"] is True
    assert json.loads(tools.list_attention_items())["count"] == 0
    assert json.loads(tools.list_attention_items(status="all"))["items"][0]["resolution"] == "replied"


def test_reply_drafts_and_status(workspace: Workspace):
    tools = WorkspaceTools(workspace)
    draft = json.loads(
        tools.save_reply_draft(
            draft="Hi Sam, it's linked in bio!",
            platform="instagram",
            account_id="acc1",
            post_id="pp1",
            comment_id="c1",
            author="sam",
            comment_text="Where can I buy this?",
            rationale="direct purchase question",
        )
    )
    assert draft["status"] == "pending"
    assert json.loads(tools.list_reply_drafts())["count"] == 1
    assert workspace.set_reply_draft_status(draft["reply_draft_id"], "sent") is True
    assert json.loads(tools.list_reply_drafts())["count"] == 0
    assert json.loads(tools.list_reply_drafts(status="sent"))["count"] == 1


def test_reports_and_ideas(workspace: Workspace):
    tools = WorkspaceTools(workspace)
    assert json.loads(tools.get_latest_report())["report"] is None

    tools.save_report("Report 1", "# one")
    tools.save_report("Report 2", "# two")
    assert json.loads(tools.get_latest_report())["title"] == "Report 2"

    tools.save_content_idea(
        title="Jacket styling reel",
        hook="Three ways to wear it before 9am",
        format="reel",
        platform="instagram",
        rationale="jacket post had 3x saves and 12 purchase questions",
        experiment="post 18:00 UTC vs 09:00 UTC",
    )
    assert json.loads(tools.list_content_ideas())["ideas"][0]["format"] == "reel"


def test_webhook_event_dedupe(workspace: Workspace):
    assert workspace.record_webhook_event("evt_1", "comment.received") is True
    assert workspace.record_webhook_event("evt_1", "comment.received") is False
    assert workspace.record_webhook_event("evt_2", "comment.received") is True
