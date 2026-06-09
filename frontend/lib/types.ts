export type BookStatus =
  | "DRAFT_BRIEF"
  | "OUTLINING"
  | "WRITING"
  | "JUDGING"
  | "REVISION"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "GENERATING_IMAGES"
  | "GENERATING_COVER"
  | "DRAFTING_METADATA"
  | "EXPORTING"
  | "EXPORT_READY"
  | "DONE"
  | "RETIRED";

export const RUNNING_STATUSES: BookStatus[] = [
  "OUTLINING",
  "WRITING",
  "JUDGING",
  "REVISION",
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
  AWAITING_APPROVAL: "Awaiting Approval",
  APPROVED: "Approved",
  GENERATING_IMAGES: "Generating Images",
  GENERATING_COVER: "Generating Cover",
  DRAFTING_METADATA: "Drafting Metadata",
  EXPORTING: "Exporting",
  EXPORT_READY: "Export Ready",
  DONE: "Done",
  RETIRED: "Retired",
};

export type StatusColor = "green" | "yellow" | "blue" | "red";

export function statusColor(s: BookStatus): StatusColor {
  if (s === "AWAITING_APPROVAL") return "blue";
  if (s === "RETIRED") return "red";
  if ((RUNNING_STATUSES as string[]).includes(s)) return "yellow";
  return "green";
}

export interface Book {
  id: string;
  title: string | null;
  status: BookStatus;
  current_round: number;
  max_rounds: number;
  score_threshold: number;
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
