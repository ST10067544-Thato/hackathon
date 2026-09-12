# Creator Companion — agents inside a creator's social inbox

A Python [Agno](https://docs.agno.com) team served by AgentOS. It reads a creator's
connected accounts through [Zernio](https://docs.zernio.com), triages comments as they
arrive, and turns comments plus analytics into a report, reply drafts, and next content
ideas. Every write to a social account pauses for the creator's approval.

| Member | Role | Tools |
|---|---|---|
| **Social Monitor** | Retrieve posts, comments, analytics | Zernio read-only: accounts, posts, platform posts, analytics, timeline, follower stats, commented posts, comments |
| **Community Advisor** | Find comments that need attention, draft replies | Zernio comments · `reply_to_comment` (approval-gated) · workspace: `flag_for_attention`, `save_reply_draft` |
| **Content Strategist** | Turn signals into content advice | Zernio analytics + best-time · `create_post_draft` (approval-gated, drafts only) · workspace: `save_content_idea` · Exa search when `EXA_API_KEY` is set |
| **Web Scout** (optional) | Read public pages the APIs can't see, in a real browser | `browse_page(url, goal)` — a [browser-use](https://github.com/browser-use/browser-use) agent: read-only, one page per call, structured findings |
| **Creator Companion** (team) | Coordinates and writes the report | workspace: `save_report`, `get_latest_report`, list drafts/ideas/attention |

The team's outputs are kept in a local workspace (`data/workspace.db`) and can be read
back over HTTP, so a web page or a browser agent can show them later.

## Run it

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Credentials go in the
repository root `.env`, like the other apps.

```dotenv
# model (same variables as the rest of the kit)
MODEL_PROVIDER=google            # openai | openrouter | google (alias: gemini)
GOOGLE_API_KEY=AIza...           # https://aistudio.google.com/apikey (GEMINI_API_KEY also accepted)
MODEL=gemini-3.6-flash           # any tool-capable model available to your account

# Zernio
ZERNIO_API_KEY=sk_...            # https://zernio.com/dashboard → API keys
ZERNIO_WEBHOOK_SECRET=...        # the secret you send when creating the webhook
ZERNIO_PROFILE_ID=               # optional: scope every call to one profile

# optional
EXA_API_KEY=...                  # gives the strategist web research
BROWSER_USE_API_KEY=bu_...       # Web Scout uses Browser Use's hosted model (bu-latest) instead of MODEL
BROWSER_USE_CLOUD=0              # 1 = hosted browsers on that key; 0 = local headless Chrome (default)
BROWSER_SCOUT=auto               # auto | on | off — auto enables the scout when the extra is installed
BROWSER_MAX_STEPS=12             # also BROWSER_TIMEOUT_SECONDS=180, BROWSER_HEADLESS=1
BROWSER_MODEL=                   # defaults to MODEL; set a cheaper model to drive the browser
BROWSER_MAX_COMPLETION_TOKENS=1024   # per browsing step; raise only if steps get truncated
BROWSER_VISION=1                 # 0 = DOM only, much smaller prompts on a tight token budget
DATABASE_URL=postgresql+psycopg://...   # otherwise SQLite in apps/creator-companion/data/
CREATOR_COMPANION_PORT=7777
```

```bash
npm run dev:agents        # from the repo root; same as: uv run --directory apps/creator-companion creator-companion
npm run test:agents       # pytest, offline (Zernio and the model are mocked)
```

AgentOS listens on `http://localhost:7777`. Open the interactive docs at
`/docs`, or connect the [AgentOS UI](https://os.agno.com) to that URL to chat with the
team, approve paused tool calls, and manage schedules.

### Use it in the web app

The kit's web app has a Creator Companion page that talks to this service over
[AG-UI](https://docs.ag-ui.com): the team is exposed at `POST /agui` and each member at
`/members/<agent-id>/agui`, and the CopilotKit runtime in `apps/web` registers them as
`HttpAgent`s (`creatorCompanion`, `socialMonitor`, `communityAdvisor`, `contentStrategist`).

```bash
npm run dev:agents   # terminal 1 — this service on :7777
npm run dev:web      # terminal 2 — Next.js on :3100
open http://localhost:3100/creator
```

On that page: pick who to talk to, use the suggestion chips, and watch the left panel —
it reads `/workspace/*` through the Next proxy (`/api/creator/workspace/...`) and
refreshes every 10 s. When an agent calls `reply_to_comment` or `create_post_draft`, an
approval card appears in the chat; **Post reply** / **Save draft** answers the paused
call with `{"accepted": true}` and Agno resumes it, anything else rejects it. The card
is registered with `available: false` so its definition is never sent to the agent —
otherwise Agno would append it as a frontend tool and shadow the real Zernio tool.

Set `CREATOR_COMPANION_URL` in root `.env` if the service runs somewhere other than
`http://127.0.0.1:7777`.

### Ask for a report

```bash
curl -s -X POST http://localhost:7777/teams/creator-companion/runs \
  -F message="Review the last 7 days across all connected accounts. Lead with what needs my attention." \
  -F session_id=demo
```

The final report is also saved: `GET /workspace/reports/latest`.

### Approve a reply

Ask the team to reply ("Reply to @sam's question with the shop link") and the
Community Advisor calls `reply_to_comment`; the run pauses. List and resolve paused
runs at `GET /approvals` / `POST /approvals/{id}/approve`, or approve from the AgentOS UI.
Nothing is published until that approval. The same applies to `create_post_draft`,
which only ever creates a Zernio draft (`isDraft: true`), never a publish.

### Live comments via webhook

Point a Zernio webhook at `POST /webhooks/zernio` with the `comment.received` event
and your `ZERNIO_WEBHOOK_SECRET` ([docs](https://docs.zernio.com/webhooks)):

```bash
curl -s -X POST https://zernio.com/api/v1/webhooks/settings \
  -H "Authorization: Bearer $ZERNIO_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"creator-companion","url":"https://<public-host>/webhooks/zernio","events":["comment.received"],"secret":"'"$ZERNIO_WEBHOOK_SECRET"'"}'
```

Deliveries are verified with the `X-Zernio-Signature` HMAC, deduplicated by event id,
and answered `202` immediately; the team triages the comment in the background
(flags it and saves a reply draft, never replies on its own). Bad signatures get `401`;
a missing secret gets `503`. Use a tunnel (e.g. `ngrok http 7777`) for a public URL.

### Daily report on a schedule

```bash
curl -s -X POST http://localhost:7777/schedules -H "Content-Type: application/json" -d '{
  "name": "daily-creator-report",
  "cron_expr": "0 8 * * *",
  "timezone": "Africa/Johannesburg",
  "endpoint": "/teams/creator-companion/runs",
  "payload": {"message": "Produce today'"'"'s monitoring report for the last 24 hours across all connected accounts.", "session_id": "daily-report"}
}'
```

`POST /schedules/{id}/trigger` runs it now.

### Read back what the team produced

| Endpoint | Returns |
|---|---|
| `GET /workspace/attention?status=open` | Items the creator should look at |
| `GET /workspace/drafts?status=pending` | Suggested replies awaiting review |
| `POST /workspace/drafts/{id}/status?status=sent` | Mark a draft `sent` or `dismissed` |
| `GET /workspace/ideas` | Content ideas with hook, format, rationale, experiment |
| `GET /workspace/reports/latest` | Most recent saved report (Markdown) |

### Web Scout (browser-use)

The fourth member is a [browser-use](https://docs.browser-use.com) agent wrapped as one
Agno tool, adapted from browser-use's "check the visa appointment page" example: instead
of one fixed URL and a "this month, then next month" task, `browse_page(url, goal)` opens
any public page in a headless browser with vision and returns structured findings
(`answer`, `key_points`, `metrics`, `links`, `blocked`, `caveats`). It covers what the
Zernio API can't: a competitor's or peer's public profile, the creator's link-in-bio, a
hashtag or trend page, a post linked in a comment.

```bash
uv sync --extra browser          # installs browser-use; the scout appears on next start
```

Guard rails: http(s) to public hosts only (no localhost/private IPs), a step and time
budget per run, the browser session is created and closed per call, and the task text
forbids logging in or clicking anything that posts, likes, follows, subscribes, or buys.
Failures (login wall, captcha, timeout, LLM error) come back as structured errors the
agent can report, never as a crashed run.

Model: with `BROWSER_USE_API_KEY` set the scout tries Browser Use's hosted `bu-latest`
(billed to that key); otherwise it uses the same `MODEL_PROVIDER`/`MODEL` as the chat —
Gemini via `ChatGoogle` when the provider is `google` — capped at
`BROWSER_MAX_COMPLETION_TOKENS` per step. A hosted key that the LLM gateway refuses (free
tier) is detected and the run is redone once on your provider model, which is then used for
the rest of the process. Set `BROWSER_USE_CLOUD=1` to run the browser in Browser Use Cloud
instead of locally.

The local browser is **Chromium** — the build installed by `browser-use install`, pinned
with `channel="chromium"`. It is deliberately never your own Google Chrome, whose profile
carries your real cookies and logged-in sessions into what must be an anonymous read-only
visit. Run `uv run browser-use install` once to fetch it.

When the model behind the browser runs out of credit or quota, `browse_page` returns
`{"error": true, "code": "model_quota", ...}` naming the billing problem, rather than
reporting that the page was blocked.

## Layout

```
creator_companion/
  config.py            root .env loading, Settings
  zernio.py            HTTP client + error → tool-result mapping
  tools/zernio_tools.py   Zernio toolkit (paths from docs.zernio.com)
  tools/workspace.py      SQLite workspace + toolkit
  tools/web_scout.py      browser-use agent as a tool (optional `browser` extra)
  agents.py            members, team, model factory
  webhooks.py          /webhooks/zernio and /workspace/* routes
  app.py               AgentOS assembly, AG-UI interfaces, entrypoint
tests/                 offline tests (httpx MockTransport, FastAPI TestClient)
```

## Boundaries and limits

- Zernio caches comment and analytics reads for up to 10 minutes; the webhook is the
  real-time path. Analytics may answer `202 sync_pending`; agents are told to say so.
- Tool errors come back as `{"error": true, "status", "code", "hint"}` so the report
  can explain a `401` (reconnect the account), `403` (add-on/permission), or `429`.
- Only two tools write to a platform, both approval-gated: `reply_to_comment` and
  `create_post_draft`. Publishing posts is intentionally not exposed. The Web Scout is
  read-only by construction and never authenticates.
- The Zernio endpoints used are the documented ones; do not add a tool without
  checking its reference page.
