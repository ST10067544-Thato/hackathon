"use client";

/**
 * What the team produced, read back from the Creator Companion workspace.
 *
 * Attention items, reply drafts, content ideas, and the latest report are the
 * durable result of a run: they live in the service's SQLite file and survive a
 * refresh. The panel polls while the page is open so a finished run shows up
 * without a reload, and the draft buttons only change local workspace status —
 * they never post anything.
 */
import { useCallback, useEffect, useState } from "react";
import type { AttentionItem, ContentIdea, ReplyDraft, Report } from "@/lib/creator-companion";

type Workspace = {
  attention: AttentionItem[];
  drafts: ReplyDraft[];
  ideas: ContentIdea[];
  report: Report | null;
};

type LoadState =
  | { status: "loading" }
  | { status: "offline"; hint: string }
  | { status: "ready"; data: Workspace; fetchedAt: Date };

const POLL_MS = 10_000;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/creator/workspace/${path}`, { cache: "no-store" });
  if (response.status === 404) return null as T;
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.hint ?? body?.error ?? `HTTP ${response.status}`);
  }
  return body as T;
}

async function loadWorkspace(): Promise<Workspace> {
  const [attention, drafts, ideas, report] = await Promise.all([
    getJson<{ items: AttentionItem[] }>("attention?status=open&limit=20"),
    getJson<{ drafts: ReplyDraft[] }>("drafts?status=pending&limit=20"),
    getJson<{ ideas: ContentIdea[] }>("ideas?limit=10"),
    getJson<Report | null>("reports/latest"),
  ]);
  return { attention: attention.items, drafts: drafts.drafts, ideas: ideas.ideas, report };
}

export function useCreatorWorkspace() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const refresh = useCallback(async () => {
    try {
      const data = await loadWorkspace();
      setState({ status: "ready", data, fetchedAt: new Date() });
    } catch (error) {
      setState({
        status: "offline",
        hint: error instanceof Error ? error.message : "Creator Companion is not reachable.",
      });
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  return { state, refresh };
}

export function CreatorWorkspace({
  state,
  refresh,
}: {
  state: LoadState;
  refresh: () => Promise<void>;
}) {
  const [busyDraft, setBusyDraft] = useState<number | null>(null);

  const setDraftStatus = useCallback(
    async (id: number, status: "sent" | "dismissed") => {
      setBusyDraft(id);
      try {
        await fetch(`/api/creator/workspace/drafts/${id}/status?status=${status}`, { method: "POST" });
        await refresh();
      } finally {
        setBusyDraft(null);
      }
    },
    [refresh],
  );

  if (state.status === "loading") {
    return <p className="ck-muted">Loading the workspace…</p>;
  }
  if (state.status === "offline") {
    return (
      <div className="ck-setup-note">
        <p>
          <strong>Creator Companion is offline.</strong> {state.hint}
        </p>
        <p className="ck-muted">
          From the repo root: <code>npm run dev:agents</code>
        </p>
      </div>
    );
  }

  const { attention, drafts, ideas, report } = state.data;

  return (
    <div className="ck-followups">
      <div className="ck-followups-header">
        <h3>Needs attention</h3>
        <span className="ck-muted">
          {state.fetchedAt.toLocaleTimeString()}{" "}
          <button type="button" className="ck-btn ck-btn--tiny" onClick={() => void refresh()}>
            Refresh
          </button>
        </span>
      </div>
      {attention.length === 0 ? (
        <p className="ck-empty">Nothing open. Ask the team to review your comments.</p>
      ) : (
        <ul className="ck-task-list">
          {attention.map((item) => (
            <li key={item.id}>
              <span className={`ck-status-label ck-priority-${item.priority}`}>
                {item.priority} · {item.category}
              </span>
              <p>{item.summary}</p>
              <p className="ck-muted">
                {[item.platform, item.author ? `@${item.author}` : null].filter(Boolean).join(" · ")}
                {item.suggested_action ? ` — ${item.suggested_action}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}

      <h3>Reply drafts</h3>
      {drafts.length === 0 ? (
        <p className="ck-empty">No drafts waiting.</p>
      ) : (
        <ul className="ck-task-list">
          {drafts.map((draft) => (
            <li key={draft.id}>
              {draft.comment_text && (
                <p className="ck-muted">
                  {draft.author ? `@${draft.author}: ` : ""}“{draft.comment_text}”
                </p>
              )}
              <p className="ck-preserve-lines">{draft.draft}</p>
              <div className="ck-actions">
                <button
                  type="button"
                  className="ck-btn ck-btn--tiny"
                  disabled={busyDraft === draft.id}
                  onClick={() => void setDraftStatus(draft.id, "sent")}
                >
                  Mark sent
                </button>
                <button
                  type="button"
                  className="ck-btn ck-btn--tiny"
                  disabled={busyDraft === draft.id}
                  onClick={() => void setDraftStatus(draft.id, "dismissed")}
                >
                  Dismiss
                </button>
              </div>
              <p className="ck-local-note">
                Marking only updates this list. To publish, ask the agent to reply and approve it in the chat.
              </p>
            </li>
          ))}
        </ul>
      )}

      <h3>Content ideas</h3>
      {ideas.length === 0 ? (
        <p className="ck-empty">No ideas saved yet.</p>
      ) : (
        <ul className="ck-task-list">
          {ideas.map((idea) => (
            <li key={idea.id}>
              <strong>{idea.title}</strong>
              <p className="ck-muted">
                {idea.format} · {idea.platform}
              </p>
              <p>{idea.hook}</p>
              <p className="ck-muted">{idea.rationale}</p>
              {idea.experiment && <p className="ck-muted">Experiment: {idea.experiment}</p>}
            </li>
          ))}
        </ul>
      )}

      <h3>Latest report</h3>
      {report ? (
        <details className="ck-more">
          <summary>
            {report.title} · {new Date(report.created_at).toLocaleString()}
          </summary>
          <pre className="ck-transcript ck-report">{report.markdown}</pre>
        </details>
      ) : (
        <p className="ck-empty">No report saved yet.</p>
      )}
    </div>
  );
}
