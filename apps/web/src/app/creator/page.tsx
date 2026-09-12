"use client";

/**
 * Creator Companion — the web surface for the Agno team in apps/creator-companion.
 *
 * Left: what the team produced (durable, read back from the service).
 * Right: chat with the whole team or one member. The runtime forwards the
 * conversation to the Python AgentOS over AG-UI; the two account writes pause
 * for the approval cards in `CreatorApprovals`.
 */
import { useEffect, useMemo, useState } from "react";
import { CopilotChat, useAgentContext, useConfigureSuggestions } from "@copilotkit/react-core/v2";
import { CreatorApprovals } from "@/components/creator-approvals";
import { CreatorWorkspace, useCreatorWorkspace } from "@/components/creator-workspace";
import { CREATOR_AGENTS, CREATOR_SUGGESTIONS, type CreatorAgentId } from "@/lib/creator-companion";

/**
 * Which of `CREATOR_AGENTS` the service actually mounted.
 *
 * Web Scout is optional in the Python service (the `browser` extra), so its
 * AG-UI route does not exist unless it was built. Asking `/members` keeps the
 * picker from offering an agent whose first message would 404. Until the answer
 * arrives — or if the service is unreachable — the picker shows the three
 * members that are always present.
 */
function useAvailableAgents() {
  const [aguiPaths, setAguiPaths] = useState<string[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/creator/members", { cache: "no-store" });
        if (!response.ok) return;
        const body = (await response.json()) as { members?: { agui?: string }[] };
        const paths = (body.members ?? []).map((member) => member.agui).filter((p): p is string => !!p);
        if (!cancelled) setAguiPaths(paths);
      } catch {
        // Service not running; fall back to the always-present members.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return useMemo(
    () =>
      CREATOR_AGENTS.filter((entry) =>
        entry.path === "/agui" ? true : aguiPaths ? aguiPaths.includes(entry.path) : entry.id !== "webScout",
      ),
    [aguiPaths],
  );
}

export default function CreatorPage() {
  const agents = useAvailableAgents();
  const [agentId, setAgentId] = useState<CreatorAgentId>(CREATOR_AGENTS[0].id);
  const agent = agents.find((entry) => entry.id === agentId) ?? CREATOR_AGENTS[0];
  const workspace = useCreatorWorkspace();

  // If the selected member disappears (service restarted without the scout),
  // fall back to the team rather than talking to a route that is gone.
  useEffect(() => {
    if (!agents.some((entry) => entry.id === agentId)) setAgentId(CREATOR_AGENTS[0].id);
  }, [agents, agentId]);

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
                  {agents.map((entry) => (
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
