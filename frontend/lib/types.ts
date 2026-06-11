export type BookStatus =
  | "DRAFT_BRIEF"
  | "OUTLINING"
  | "WRITING"
  | "JUDGING"
  | "REVISION"
  | "AWAITING_SHORTLIST"
  | "SHORTLIST_JUDGING"
  | "AWAITING_FINAL_APPROVAL"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "GENERATING_IMAGES"
  | "GENERATING_COVER"
  | "DRAFTING_METADATA"
  | "EXPORTING"
  | "EXPORT_READY"
  | "DONE"
  | "RETIRED"
  | "CANCELLED";

export const RUNNING_STATUSES: BookStatus[] = [
  "OUTLINING",
  "WRITING",
  "JUDGING",
  "REVISION",
  "SHORTLIST_JUDGING",
  "GENERATING_IMAGES",
  "GENERATING_COVER",
  "DRAFTING_METADATA",
  "EXPORTING",
];

export const STATUS_LABEL: Record<BookStatus, string> = {
  DRAFT_BRIEF: "Draft Brief",
  OUTLINING: "Outlining",
  WRITING: "Writing",
  JUDGING: "Judging",
  REVISION: "Revision",
  AWAITING_SHORTLIST: "Awaiting Shortlist",
  SHORTLIST_JUDGING: "Shortlist Judging",
  AWAITING_FINAL_APPROVAL: "Awaiting Final Approval",
  AWAITING_APPROVAL: "Awaiting Approval",
  APPROVED: "Approved",
  GENERATING_IMAGES: "Generating Images",
  GENERATING_COVER: "Generating Cover",
  DRAFTING_METADATA: "Drafting Metadata",
  EXPORTING: "Exporting",
  EXPORT_READY: "Export Ready",
  DONE: "Done",
  RETIRED: "Retired",
  CANCELLED: "Cancelled",
};

// gray = queued/new or cancelled (neutral); green is reserved for finished.
export type StatusColor = "green" | "yellow" | "blue" | "red" | "gray";

export function statusColor(s: BookStatus): StatusColor {
  if (
    s === "AWAITING_APPROVAL" ||
    s === "AWAITING_SHORTLIST" ||
    s === "AWAITING_FINAL_APPROVAL"
  )
    return "blue";
  if (s === "RETIRED") return "red";
  if (s === "CANCELLED" || s === "DRAFT_BRIEF") return "gray";
  if (s === "EXPORT_READY" || s === "DONE") return "green";
  // Everything else is an active worker stage (incl. APPROVED, OUTLINING).
  return "yellow";
}

export interface Book {
  id: string;
  title: string | null;
  status: BookStatus;
  current_round: number;
  max_rounds: number;
  score_threshold: number;
  cancel_requested?: boolean;
  created_at: string;
  updated_at: string;
}

export interface Judgement {
  id: string;
  story_version_id: string;
  round: number;
  emotional_authenticity: number;
  representation_quality: number;
  pacing: number;
  age_fit: number;
  uniqueness: number;
  weighted_total: number;
  passed: boolean;
  critique: Record<string, string>;
  created_at: string;
}

export interface StoryVersion {
  id: string;
  round: number;
  method: string;
  content: string;
  shortlisted: boolean;
  judgements: Judgement[];
  created_at: string;
}

export interface BookMetadata {
  title?: string;
  subtitle?: string;
  author?: string;
  description?: string;
  keywords?: string[];
  age_range?: string;
  series_name?: string;
}

export interface PipelineEvent {
  type: string;
  status?: string;
  actor?: string;
  round?: number;
  message?: string;
  [key: string]: unknown;
}

export interface PreflightIssue {
  check: string;
  spread_index: number | null;
  detail: string;
}

export interface PreflightReport {
  passed: boolean;
  page_count: number | null;
  issues: PreflightIssue[];
}

export interface PreviewInfo {
  count: number;
  preflight: PreflightReport | null;
}

export interface CreateBookPayload {
  title: string;
  brief: {
    description: string;
    characters: string;
    setting: string;
    age_range: string;
    theme?: string;
  };
  max_rounds: number;
  score_threshold: number;
}
