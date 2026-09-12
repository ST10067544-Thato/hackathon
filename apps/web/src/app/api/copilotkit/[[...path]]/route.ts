/**
 * The web surface's runtime endpoint.
 *
 * A Hono app built at module scope; Next.js route handlers are fetch-based, so
 * `app.fetch` is the handler. The catch-all segment lets Hono route the
 * runtime's sub-paths itself.
 *
 * TWO THINGS TO NOT DO HERE:
 *
 * 1. Do NOT declare `channels` on this runtime, and never call
 *    `app.channels.ready()`. Next.js isolates freeze and recycle per request,
 *    so a cold start would mint a competing listener for the same Channel —
 *    and managed delivery is claim-based, so the loser silently gets nothing.
 *    The Channels listener is `apps/channel`, a long-running process.
 *
 * 2. Do NOT reuse one agent instance across requests. The factory form hands
 *    out a fresh agent per resolution.
 *
 * Besides the built-in incident agent (`default`), the runtime registers the
 * Creator Companion team and its members. They run in the Python AgentOS
 * (apps/creator-companion) and speak AG-UI, so each is a plain `HttpAgent`
 * pointed at that service — the runtime streams events through unchanged, and
 * approval pauses arrive as tool calls the page answers (see
 * components/creator-approvals.tsx).
 */
import { randomUUID } from "node:crypto";
import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotHonoHandler,
} from "@copilotkit/runtime/v2";
import { makeAgent } from "agent-core";
import { CREATOR_AGENTS } from "@/lib/creator-companion";
import { creatorCompanionUrl } from "@/lib/server/creator-companion";

function creatorAgents() {
  const base = creatorCompanionUrl();
  return Object.fromEntries(
    CREATOR_AGENTS.map(({ id, path }) => [id, new HttpAgent({ url: `${base}${path}` })]),
  );
}

// Web writes use /api/followups after a browser approval. Never expose raw MCP writes here.
const runtime = new CopilotRuntime({
  agents: () => ({
    default: makeAgent(randomUUID(), { workplace: false }),
    ...creatorAgents(),
  }),
});

const app = createCopilotHonoHandler({
  runtime,
  basePath: "/api/copilotkit",
});

export const GET = app.fetch;
export const POST = app.fetch;
export const OPTIONS = app.fetch;
