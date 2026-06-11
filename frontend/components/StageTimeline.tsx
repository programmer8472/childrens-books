"use client";

import type { Book, BookStatus, PipelineEvent } from "@/lib/types";

// Canonical pipeline as the human reads it. Several BookStatus values collapse
// into one visible step (e.g. OUTLINING+WRITING → "Write"; the JUDGING/REVISION
// loop → "Judge").
type Step = { key: string; label: string; gate?: boolean };

const STEPS: Step[] = [
  { key: "brief", label: "Brief" },
  { key: "write", label: "Write" },
  { key: "judge", label: "Judge" },
  { key: "shortlist", label: "Select shortlist", gate: true },
  { key: "rejudge", label: "Re-judge" },
  { key: "approve", label: "Final pick", gate: true },
  { key: "illustrate", label: "Illustrate" },
  { key: "cover", label: "Cover" },
  { key: "metadata", label: "Metadata" },
  { key: "export", label: "Export" },
  { key: "ready", label: "Ready" },
];

const STATUS_STEP: Record<BookStatus, number> = {
  DRAFT_BRIEF: 0,
  OUTLINING: 1,
  WRITING: 1,
  JUDGING: 2,
  REVISION: 2,
  AWAITING_SHORTLIST: 3,
  SHORTLIST_JUDGING: 4,
  AWAITING_FINAL_APPROVAL: 5,
  AWAITING_APPROVAL: 5,
  APPROVED: 6,
  GENERATING_IMAGES: 6,
  GENERATING_COVER: 7,
  DRAFTING_METADATA: 8,
  EXPORTING: 9,
  EXPORT_READY: 10,
  DONE: 10,
  RETIRED: -1,
  CANCELLED: -1,
};

function latestProgress(events: PipelineEvent[]): { current: number; total: number } | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "progress" && typeof e.current === "number" && typeof e.total === "number") {
      return { current: e.current, total: e.total };
    }
  }
  return null;
}

export function StageTimeline({
  book,
  events,
}: {
  book: Book;
  events: PipelineEvent[];
}) {
  const terminal = book.status === "RETIRED" || book.status === "CANCELLED";
  const cur = STATUS_STEP[book.status];
  const progress = latestProgress(events);
  const inLoop = book.status === "WRITING" || book.status === "JUDGING" || book.status === "REVISION";

  return (
    <div className="rounded-xl bg-gray-800/40 border border-gray-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-200">Pipeline</h3>
        {terminal && (
          <span
            className={`text-xs font-medium px-2.5 py-1 rounded-full ${
              book.status === "RETIRED"
                ? "bg-red-500/15 text-red-400 border border-red-500/30"
                : "bg-gray-600/30 text-gray-300 border border-gray-500/30"
            }`}
          >
            {book.status === "RETIRED" ? "Failed / Retired" : "Cancelled"}
          </span>
        )}
      </div>

      <ol className={terminal ? "space-y-0 opacity-60" : "space-y-0"}>
        {STEPS.map((step, i) => {
          const state =
            terminal ? (i <= 1 ? "done" : "skipped")
            : i < cur ? "done"
            : i === cur ? "current"
            : "upcoming";
          const isLast = i === STEPS.length - 1;
          const showImageBar = state === "current" && step.key === "illustrate" && progress;
          const showRound = state === "current" && inLoop && step.key !== "brief";

          return (
            <li key={step.key} className="flex gap-3">
              {/* Rail + node */}
              <div className="flex flex-col items-center">
                <span
                  className={`mt-0.5 h-5 w-5 rounded-full flex items-center justify-center text-[10px] flex-shrink-0 ${
                    state === "done"
                      ? "bg-green-500/20 text-green-400 border border-green-500/40"
                      : state === "current"
                      ? step.gate
                        ? "bg-blue-500/20 text-blue-300 border border-blue-400/60 animate-pulse"
                        : "bg-amber-500/20 text-amber-300 border border-amber-400/60 animate-pulse"
                      : "bg-gray-700/40 text-gray-600 border border-gray-700"
                  }`}
                >
                  {state === "done" ? "✓" : step.gate && state === "current" ? "!" : ""}
                </span>
                {!isLast && (
                  <span
                    className={`w-px flex-1 my-0.5 ${
                      state === "done" ? "bg-green-500/30" : "bg-gray-700"
                    }`}
                    style={{ minHeight: 18 }}
                  />
                )}
              </div>

              {/* Label + live detail */}
              <div className="pb-3 flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-sm ${
                      state === "current"
                        ? step.gate
                          ? "text-blue-200 font-semibold"
                          : "text-amber-200 font-semibold"
                        : state === "done"
                        ? "text-gray-300"
                        : "text-gray-600"
                    }`}
                  >
                    {step.label}
                  </span>
                  {state === "current" && step.gate && (
                    <span className="text-[10px] uppercase tracking-wide text-blue-400">
                      waiting on you
                    </span>
                  )}
                  {showRound && (
                    <span className="text-[10px] text-amber-400/80 tabular-nums">
                      round {book.current_round}/{book.max_rounds}
                    </span>
                  )}
                </div>
                {showImageBar && progress && (
                  <div className="mt-1.5 flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden max-w-[200px]">
                      <div
                        className="h-full bg-amber-500 rounded-full transition-all"
                        style={{ width: `${Math.round((progress.current / progress.total) * 100)}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-amber-400/80 tabular-nums">
                      {progress.current}/{progress.total}
                    </span>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
