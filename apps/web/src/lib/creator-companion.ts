/**
 * Shared knowledge about the Creator Companion service (apps/creator-companion).
 *
 * The Python AgentOS exposes the team and each member over AG-UI. The keys here
 * are the agent ids the CopilotKit runtime registers and the page selects from.
 */
export const CREATOR_AGENTS = [
  {
    id: "creatorCompanion",
    label: "Creator Companion",
    blurb: "The whole team: attention items, performance, next actions.",
    path: "/agui",
  },
  {
    id: "socialMonitor",
    label: "Social Monitor",
    blurb: "Read-only: posts, comments, analytics, followers.",
    path: "/members/social-monitor/agui",
  },
  {
    id: "communityAdvisor",
    label: "Community Advisor",
    blurb: "Triage comments and draft replies. Replying needs your approval.",
    path: "/members/community-advisor/agui",
  },
  {
    id: "contentStrategist",
    label: "Content Strategist",
    blurb: "Content ideas, hooks, timing. Saving a draft needs your approval.",
    path: "/members/content-strategist/agui",
  },
  {
    id: "webScout",
    label: "Web Scout",
    blurb: "Opens a public page in a real browser — a competitor profile, your link-in-bio, a trend page — and reports back. Read-only.",
    path: "/members/web-scout/agui",
  },
] as const;

export type CreatorAgentId = (typeof CREATOR_AGENTS)[number]["id"];

export const CREATOR_SUGGESTIONS = [
  {
    title: "What needs my attention?",
    message:
      "Review comments across my connected accounts from the last 7 days. Lead with questions, complaints, and collaboration offers, and save a reply draft for each one worth answering.",
  },
  {
    title: "How did my posts do?",
    message:
      "Summarize post performance for the last 14 days: top posts, what changed, and anything under-performing. Numbers only from the tools.",
  },
  {
    title: "Give me 3 content ideas",
    message:
      "Based on what performed and what people are asking in the comments, propose three concrete next posts with hooks and one experiment. Save each idea.",
  },
] as const;

/** Rows returned by the service's /workspace endpoints (see creator_companion/tools/workspace.py). */
export type AttentionItem = {
  id: number;
  created_at: string;
  status: "open" | "resolved";
  priority: "high" | "medium" | "low";
  category: string;
  platform: string | null;
  author: string | null;
  summary: string;
  suggested_action: string | null;
};

export type ReplyDraft = {
  id: number;
  created_at: string;
  status: "pending" | "sent" | "dismissed";
  platform: string;
  author: string | null;
  comment_text: string | null;
  draft: string;
  rationale: string | null;
};

export type ContentIdea = {
  id: number;
  created_at: string;
  title: string;
  hook: string;
  format: string;
  platform: string;
  rationale: string;
  experiment: string | null;
};

export type Report = { id: number; created_at: string; title: string; markdown: string };
