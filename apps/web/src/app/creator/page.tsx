"use client";

/**
 * Creator Companion — the web surface for the Agno team in apps/creator-companion.
 *
 * Left: what the team produced (durable, read back from the service).
 * Right: chat with the whole team or one member. The runtime forwards the
 * conversation to the Python AgentOS over AG-UI; the two account writes pause
 * for the approval cards in `CreatorApprovals`.
 */
import { useState } from "react";
import { CopilotChat, useAgentContext, useConfigureSuggestions } from "@copilotkit/react-core/v2";
import { CreatorApprovals } from "@/components/creator-approvals";
import { CreatorWorkspace, useCreatorWorkspace } from "@/components/creator-workspace";
import { CREATOR_AGENTS, CREATOR_SUGGESTIONS, type CreatorAgentId } from "@/lib/creator-companion";

export default function CreatorPage() {
  const [agentId, setAgentId] = useState<CreatorAgentId>(CREATOR_AGENTS[0].id);
  const agent = CREATOR_AGENTS.find((entry) => entry.id === agentId) ?? CREATOR_AGENTS[0];
  const workspace = useCreatorWorkspace();

  useConfigureSuggestions(
    { suggestions: [...CREATOR_SUGGESTIONS], available: "before-first-message", consumerAgentId: agentId },
    [agentId],
  );

  useAgentContext({
    description:
      "The creator's workspace as shown on this page: open attention items, pending reply drafts, and saved ideas. Counts only; use the workspace tools for details.",
    value:
      workspace.state.status === "ready"
        ? {
            openAttentionItems: workspace.state.data.attention.length,
            pendingReplyDrafts: workspace.state.data.drafts.length,
            savedIdeas: workspace.state.data.ideas.length,
            latestReport: workspace.state.data.report?.title ?? null,
          }
        : { workspace: workspace.state.status },
  });

  return (
    <>
      <CreatorApprovals onDecided={() => void workspace.refresh()} />
      <main className="ck-workspace">
        <header className="ck-workspace-header">
          <div>
            <p className="ck-eyebrow">Agents, everywhere · Creator Companion</p>
            <h1>Your social inbox, triaged</h1>
            <p className="ck-intro">
              Ask what needs attention. Review drafts. Approve replies before they go out.
            </p>
          </div>
          <a className="ck-tag" href="/">
            Incident example →
          </a>
        </header>

        <div className="ck-workspace-grid">
          <section className="ck-panel" aria-labelledby="workspace-title">
            <h2 id="workspace-title">From the team</h2>
            <CreatorWorkspace state={workspace.state} refresh={workspace.refresh} />
          </section>

          <section className="ck-panel ck-assistant" aria-labelledby="assistant-title">
            <header className="ck-assistant-header">
              <div className="ck-incident-picker">
                <label htmlFor="agent-select">Talk to</label>
                <select
                  id="agent-select"
                  value={agentId}
                  onChange={(event) => setAgentId(event.target.value as CreatorAgentId)}
                >
                  {CREATOR_AGENTS.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.label}
                    </option>
                  ))}
                </select>
              </div>
              <h2 id="assistant-title">{agent.label}</h2>
              <p>{agent.blurb}</p>
            </header>
            <CopilotChat
              key={agentId}
              agentId={agentId}
              threadId={`creator-${agentId}`}
              className="ck-chat"
              labels={{
                welcomeMessageText: "What needs attention?",
                chatInputPlaceholder: `Ask ${agent.label}…`,
              }}
            />
          </section>
        </div>
      </main>
    </>
  );
}
