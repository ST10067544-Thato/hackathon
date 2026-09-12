/**
 * Server-only: where the Creator Companion AgentOS lives.
 *
 * Read lazily so the value comes from root `.env` at request time, not at
 * module load during `next build`.
 */
export function creatorCompanionUrl(): string {
  return (process.env.CREATOR_COMPANION_URL?.trim() || "http://127.0.0.1:7777").replace(/\/+$/, "");
}
