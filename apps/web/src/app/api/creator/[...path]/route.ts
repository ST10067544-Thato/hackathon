/**
 * Read-back proxy for the Creator Companion workspace.
 *
 * The browser cannot call the Python service directly (different origin, no
 * CORS entry for :3100), so this forwards `/api/creator/workspace/...` to the
 * service's `/workspace/...` and returns its JSON untouched. Only GET, plus the
 * one POST that marks a draft sent/dismissed. Nothing here talks to a social
 * platform.
 */
import { creatorCompanionUrl } from "@/lib/server/creator-companion";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALLOWED = /^workspace\/(attention|drafts|ideas|reports|reports\/latest|drafts\/\d+\/status)$/;

async function forward(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = path.join("/");
  if (!ALLOWED.test(target)) {
    return Response.json({ error: "not found" }, { status: 404 });
  }
  const url = new URL(`${creatorCompanionUrl()}/${target}`);
  url.search = new URL(request.url).search;
  try {
    const upstream = await fetch(url, { method: request.method, cache: "no-store" });
    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (error) {
    return Response.json(
      {
        error: "creator companion unreachable",
        detail: error instanceof Error ? error.message : String(error),
        hint: "Start it with `npm run dev:agents` (or set CREATOR_COMPANION_URL).",
      },
      { status: 503 },
    );
  }
}

export const GET = forward;
export const POST = forward;
