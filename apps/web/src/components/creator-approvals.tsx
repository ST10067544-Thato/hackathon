"use client";

/**
 * The approval gate for the Creator Companion's two account writes.
 *
 * Both tools run in the Python service with Agno's `requires_confirmation`.
 * When one is called the run pauses and Agno forwards the tool call over AG-UI;
 * CopilotKit routes it here, the creator decides, and the answer goes back as
 * the tool result — `{"accepted": true}` resumes the call, anything else
 * rejects it. Nothing is posted until the button is pressed.
 *
 * `available: false` matters: it keeps these registrations out of the tool list
 * sent to the agent (Agno would append them as frontend tools and shadow the
 * real Zernio tools) while still letting CopilotKit render and answer the
 * backend's paused call by name.
 */
import { useHumanInTheLoop } from "@copilotkit/react-core/v2";
import { z } from "zod";

const ACCEPT = JSON.stringify({ accepted: true });
const REJECT = JSON.stringify({ accepted: false, note: "The creator declined; nothing was sent." });

function GateDone({ result }: { result: unknown }) {
  const text =
    result === undefined
      ? "Waiting for the agent…"
      : typeof result === "string"
        ? result
        : JSON.stringify(result);
  return (
    <article className="ck-card ck-card--gate">
      <p className="ck-gate-done">{text}</p>
    </article>
  );
}

export function CreatorApprovals({ onDecided }: { onDecided?: () => void }) {
  useHumanInTheLoop({
    name: "reply_to_comment",
    description: "Publish a reply on the creator's behalf.",
    available: false,
    parameters: z.object({
      post_id: z.string(),
      account_id: z.string(),
      message: z.string(),
      comment_id: z.string().optional(),
    }),
    render: ({ args, respond, result }) => {
      if (!respond) return <GateDone result={result} />;
      return (
        <article className="ck-card ck-card--gate" aria-label="Approve public reply">
          <h3>Post this reply publicly?</h3>
          <p className="ck-preserve-lines">{args.message}</p>
          <dl className="ck-facts">
            <div>
              <dt>Account</dt>
              <dd>
                <code>{args.account_id}</code>
              </dd>
            </div>
            <div>
              <dt>{args.comment_id ? "Replying to comment" : "On post"}</dt>
              <dd>
                <code>{args.comment_id ?? args.post_id}</code>
              </dd>
            </div>
          </dl>
          <p className="ck-muted">This is a real write to the platform. It cannot be unsent by the agent.</p>
          <div className="ck-actions">
            <button
              type="button"
              className="ck-btn ck-btn--primary"
              onClick={() => {
                onDecided?.();
                void respond(ACCEPT);
              }}
            >
              Post reply
            </button>
            <button type="button" className="ck-btn" onClick={() => void respond(REJECT)}>
              Don&apos;t post
            </button>
          </div>
        </article>
      );
    },
  });

  useHumanInTheLoop({
    name: "create_post_draft",
    description: "Save a post idea as a Zernio draft.",
    available: false,
    parameters: z.object({
      content: z.string(),
      title: z.string().optional(),
      platform: z.string().optional(),
      account_id: z.string().optional(),
      rationale: z.string().optional(),
    }),
    render: ({ args, respond, result }) => {
      if (!respond) return <GateDone result={result} />;
      return (
        <article className="ck-card ck-card--gate" aria-label="Approve draft">
          <h3>{args.title ? `Save draft: ${args.title}` : "Save this as a draft?"}</h3>
          <p className="ck-preserve-lines">{args.content}</p>
          {args.rationale && <p className="ck-muted">{args.rationale}</p>}
          <p className="ck-muted">
            Saved as a draft in Zernio{args.platform ? ` for ${args.platform}` : ""}. Drafts never publish on their
            own.
          </p>
          <div className="ck-actions">
            <button
              type="button"
              className="ck-btn ck-btn--primary"
              onClick={() => {
                onDecided?.();
                void respond(ACCEPT);
              }}
            >
              Save draft
            </button>
            <button type="button" className="ck-btn" onClick={() => void respond(REJECT)}>
              Skip
            </button>
          </div>
        </article>
      );
    },
  });

  return null;
}
