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
| **Creator Companion** (team) | Coordinates and writes the report | workspace: `save_report`, `get_latest_report`, list drafts/ideas/attention |

The team's outputs are kept in a local workspace (`data/workspace.db`) and can be read
back over HTTP, so a web page or a browser agent can show them later.

## Run it

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Credentials go in the
repository root `.env`, like the other apps.

```dotenv
# model (same variables as the rest of the kit)
MODEL_PROVIDER=openai            # or openrouter
OPENAI_API_KEY=...
MODEL=gpt-5.4-mini               # any tool-capable model available to your account

# Zernio
ZERNIO_API_KEY=sk_...            # https://zernio.com/dashboard → API keys
ZERNIO_WEBHOOK_SECRET=...        # the secret you send when creating the webhook
ZERNIO_PROFILE_ID=               # optional: scope every call to one profile

# optional
EXA_API_KEY=...                  # gives the strategist web research
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

## Layout

```
creator_companion/
  config.py            root .env loading, Settings
  zernio.py            HTTP client + error → tool-result mapping
  tools/zernio_tools.py   Zernio toolkit (paths from docs.zernio.com)
  tools/workspace.py      SQLite workspace + toolkit
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
  `create_post_draft`. Publishing posts is intentionally not exposed.
- The Zernio endpoints used are the documented ones; do not add a tool without
  checking its reference page.
