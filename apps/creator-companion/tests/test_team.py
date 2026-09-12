from creator_companion.agents import COMMUNITY_ID, MONITOR_ID, STRATEGIST_ID, TEAM_ID


def tool_names(component) -> dict[str, bool]:
    names: dict[str, bool] = {}
    for toolkit in component.tools or []:
        for name, fn in toolkit.functions.items():
            names[name] = bool(fn.requires_confirmation)
    return names


def test_members_only_get_the_tools_their_role_needs(companion):
    assert companion.team.id == TEAM_ID
    assert [m.id for m in companion.team.members] == [MONITOR_ID, COMMUNITY_ID, STRATEGIST_ID]

    monitor = tool_names(companion.monitor)
    assert not any(monitor.values()), "the monitor is read-only"
    assert "reply_to_comment" not in monitor and "create_post_draft" not in monitor

    community = tool_names(companion.community)
    assert community["reply_to_comment"] is True
    assert {"flag_for_attention", "save_reply_draft", "get_post_comments"} <= set(community)
    assert "create_post_draft" not in community

    strategist = tool_names(companion.strategist)
    assert strategist["create_post_draft"] is True
    assert {"save_content_idea", "get_best_times_to_post", "get_post_analytics"} <= set(strategist)
    assert "reply_to_comment" not in strategist

    assert "save_report" in tool_names(companion.team)


def test_every_write_to_a_social_account_is_confirmation_gated(companion):
    writes = {
        name
        for member in companion.team.members
        for name, gated in tool_names(member).items()
        if name in ("reply_to_comment", "create_post_draft")
    }
    assert writes == {"reply_to_comment", "create_post_draft"}
    for member in companion.team.members:
        for name, gated in tool_names(member).items():
            if name in writes:
                assert gated, f"{member.id}.{name} must require confirmation"
