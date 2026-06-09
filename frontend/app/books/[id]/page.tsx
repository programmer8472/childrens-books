"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { usePolling, useBookStream } from "@/lib/hooks";
import type { Book, BookMetadata, Judgement, PipelineEvent, StoryVersion } from "@/lib/types";
import { STATUS_LABEL } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ParagraphEditor } from "@/components/ParagraphEditor";

// ---------------------------------------------------------------------------
// Judge score display
// ---------------------------------------------------------------------------

const SCORE_DIMS: { key: keyof Judgement; label: string }[] = [
  { key: "emotional_authenticity", label: "Emotional Authenticity" },
  { key: "representation_quality", label: "Representation" },
  { key: "pacing", label: "Pacing" },
  { key: "age_fit", label: "Age Fit" },
  { key: "uniqueness", label: "Uniqueness" },
];

function ScoreBar({ value }: { value: number }) {
  const pct = Math.round((value / 10) * 100);
  const color =
    value >= 8 ? "bg-green-500" : value >= 6 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 w-8 text-right tabular-nums">
        {value.toFixed(1)}
      </span>
    </div>
  );
}

function JudgeCard({ j }: { j: Judgement }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-lg bg-gray-800 border border-gray-700 p-4 space-y-2">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-gray-100">
          Score:{" "}
          <span
            className={
              j.passed ? "text-green-400" : "text-yellow-400"
            }
          >
            {j.weighted_total.toFixed(2)}
          </span>
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            j.passed
              ? "bg-green-900/50 text-green-300"
              : "bg-yellow-900/50 text-yellow-300"
          }`}
        >
          {j.passed ? "Passed" : "Not passed"}
        </span>
      </div>

      {SCORE_DIMS.map(({ key, label }) => (
        <div key={key}>
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{label}</span>
          </div>
          <ScoreBar value={j[key] as number} />
        </div>
      ))}

      {Object.keys(j.critique).length > 0 && (
        <div>
          <button
            onClick={() => setExpanded((x) => !x)}
            className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            {expanded ? "Hide" : "Show"} critique ▾
          </button>
          {expanded && (
            <div className="mt-2 space-y-2">
              {Object.entries(j.critique).map(([dim, text]) => (
                <div key={dim}>
                  <p className="text-xs font-medium text-gray-400 capitalize">
                    {dim.replace(/_/g, " ")}
                  </p>
                  <p className="text-xs text-gray-300 leading-relaxed">{text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant card (story version + its judgements)
// ---------------------------------------------------------------------------

function VersionCard({
  version,
  bookId,
  isBest,
}: {
  version: StoryVersion;
  bookId: string;
  isBest: boolean;
}) {
  const [selectedParagraph, setSelectedParagraph] = useState<string | null>(null);
  const [showFull, setShowFull] = useState(false);

  const paragraphs = version.content
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);

  const topJudgement = version.judgements.reduce<Judgement | null>(
    (best, j) =>
      best === null || j.weighted_total > best.weighted_total ? j : best,
    null
  );

  return (
    <div
      className={`rounded-xl border ${
        isBest
          ? "border-indigo-500/60 bg-indigo-950/10"
          : "border-gray-700 bg-gray-800/50"
      } overflow-hidden`}
    >
      <div className="px-5 py-3 flex items-center justify-between border-b border-gray-700/50">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-gray-400">
            {version.method}
          </span>
          {isBest && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/50 text-indigo-300 border border-indigo-700/50">
              Best
            </span>
          )}
        </div>
        {topJudgement && (
          <span className="text-sm font-semibold text-gray-200">
            {topJudgement.weighted_total.toFixed(2)}
          </span>
        )}
      </div>

      <div className="p-5 grid gap-5 lg:grid-cols-2">
        {/* Story content */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">
              Story
            </p>
            <button
              onClick={() => setShowFull((x) => !x)}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              {showFull ? "Collapse" : "Expand"}
            </button>
          </div>
          <div
            className={`space-y-2 overflow-hidden transition-all ${
              showFull ? "" : "max-h-64"
            }`}
          >
            {paragraphs.map((para, i) => (
              <p
                key={i}
                onClick={() => setSelectedParagraph(para)}
                className="text-sm text-gray-300 leading-relaxed font-mono cursor-pointer rounded px-2 py-1 -mx-2 hover:bg-indigo-900/20 hover:text-gray-100 transition-colors group relative"
                title="Click to edit"
              >
                {para}
                <span className="absolute right-2 top-1 text-xs text-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity">
                  edit ✏
                </span>
              </p>
            ))}
          </div>
          {!showFull && paragraphs.length > 3 && (
            <button
              onClick={() => setShowFull(true)}
              className="mt-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              +{paragraphs.length - 3} more paragraphs…
            </button>
          )}
        </div>

        {/* Judge scores */}
        <div>
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">
            Judge Scores
          </p>
          {topJudgement ? (
            <JudgeCard j={topJudgement} />
          ) : (
            <p className="text-sm text-gray-500 italic">No judgement yet</p>
          )}
        </div>
      </div>

      {selectedParagraph && (
        <ParagraphEditor
          bookId={bookId}
          paragraphText={selectedParagraph}
          onClose={() => setSelectedParagraph(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live event feed (WebSocket)
// ---------------------------------------------------------------------------

function EventFeed({ events, connected }: { events: PipelineEvent[]; connected: boolean }) {
  if (events.length === 0 && !connected) return null;
  return (
    <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
      <div className="px-4 py-2 border-b border-gray-800 flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            connected ? "bg-green-400 animate-pulse" : "bg-gray-600"
          }`}
        />
        <p className="text-xs font-medium text-gray-400">
          Live Feed {connected ? "(connected)" : "(disconnected)"}
        </p>
      </div>
      <div className="p-3 space-y-1 max-h-40 overflow-y-auto font-mono text-xs">
        {events.length === 0 && (
          <p className="text-gray-600 italic">Waiting for events…</p>
        )}
        {events.map((ev, i) => (
          <div key={i} className="text-gray-400">
            <span className="text-gray-600 mr-2">
              {new Date().toLocaleTimeString()}
            </span>
            <span className="text-indigo-400">{ev.type}</span>
            {ev.status && (
              <span className="text-yellow-400 ml-2">→ {ev.status}</span>
            )}
            {ev.message && (
              <span className="text-gray-500 ml-2">{ev.message}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Approval gate
// ---------------------------------------------------------------------------

function ApprovalGate({
  bookId,
  onAction,
}: {
  bookId: string;
  onAction: () => void;
}) {
  const [rejectNote, setRejectNote] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [loading, setLoading] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleApprove() {
    setLoading("approve");
    setError(null);
    try {
      await api.approveBook(bookId);
      onAction();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to approve");
      setLoading(null);
    }
  }

  async function handleReject() {
    setLoading("reject");
    setError(null);
    try {
      await api.rejectBook(bookId, rejectNote.trim() || undefined);
      onAction();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reject");
      setLoading(null);
    }
  }

  return (
    <div className="rounded-xl border-2 border-blue-500/60 bg-blue-950/20 p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="h-2.5 w-2.5 rounded-full bg-blue-400 animate-pulse" />
        <h3 className="text-base font-semibold text-blue-200">
          Approval Required
        </h3>
      </div>
      <p className="text-sm text-blue-300/80 mb-4">
        Review the story variants above. Approve to continue to image generation,
        or reject to send back for another writing round.
      </p>

      {showRejectForm ? (
        <div className="space-y-3">
          <textarea
            className="w-full rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm px-3 py-2 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-red-500 resize-none h-20"
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
            placeholder="Optional feedback for the next revision round…"
          />
          <div className="flex gap-3">
            <button
              onClick={() => setShowRejectForm(false)}
              className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleReject}
              disabled={loading === "reject"}
              className="px-4 py-2 rounded-lg bg-red-700 text-white text-sm font-medium hover:bg-red-600 disabled:opacity-50 transition-colors"
            >
              {loading === "reject" ? "Sending back…" : "Confirm Reject"}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-3">
          <button
            onClick={handleApprove}
            disabled={!!loading}
            className="flex-1 py-2.5 rounded-lg bg-green-700 text-white text-sm font-semibold hover:bg-green-600 disabled:opacity-50 transition-colors"
          >
            {loading === "approve" ? "Approving…" : "✓ Approve"}
          </button>
          <button
            onClick={() => setShowRejectForm(true)}
            disabled={!!loading}
            className="flex-1 py-2.5 rounded-lg bg-gray-700 text-gray-200 text-sm font-semibold hover:bg-gray-600 disabled:opacity-50 transition-colors"
          >
            ✗ Reject
          </button>
        </div>
      )}

      {error && (
        <p className="mt-3 text-sm text-red-400 bg-red-950/50 rounded px-3 py-2">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metadata editor (EXPORT_READY / DONE)
// ---------------------------------------------------------------------------

function MetadataPanel({
  bookId,
  initialMeta,
}: {
  bookId: string;
  initialMeta: BookMetadata;
}) {
  const [meta, setMeta] = useState<BookMetadata>(initialMeta);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await api.updateMetadata(bookId, meta);
      setMeta(updated);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const field = (key: keyof BookMetadata, label: string) => (
    <div>
      <label className="block text-xs font-medium text-gray-400 mb-1">
        {label}
      </label>
      <input
        className="w-full rounded-md bg-gray-800 border border-gray-600 text-gray-100 text-sm px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        value={(meta[key] as string) ?? ""}
        onChange={(e) => setMeta({ ...meta, [key]: e.target.value })}
      />
    </div>
  );

  return (
    <div className="rounded-xl bg-gray-800/50 border border-gray-700 p-5">
      <h3 className="text-base font-semibold text-gray-100 mb-4">
        KDP Metadata
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {field("title", "Title")}
        {field("subtitle", "Subtitle")}
        {field("author", "Author")}
        {field("age_range", "Age Range")}
        {field("series_name", "Series Name")}
      </div>
      <div className="mt-3">
        <label className="block text-xs font-medium text-gray-400 mb-1">
          Description
        </label>
        <textarea
          className="w-full rounded-md bg-gray-800 border border-gray-600 text-gray-100 text-sm px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none h-20"
          value={meta.description ?? ""}
          onChange={(e) => setMeta({ ...meta, description: e.target.value })}
        />
      </div>
      <div className="mt-3 flex items-center gap-4">
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors"
        >
          {saving ? "Saving…" : "Save Metadata"}
        </button>
        {saved && (
          <span className="text-xs text-green-400">Saved ✓</span>
        )}
        {error && (
          <span className="text-xs text-red-400">{error}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export panel
// ---------------------------------------------------------------------------

function ExportPanel({ bookId }: { bookId: string }) {
  const [manifest, setManifest] = useState<Record<string, string> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const m = await api.getExportManifest(bookId);
      setManifest(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load manifest");
    } finally {
      setLoading(false);
    }
  }

  const ARTIFACT_LABELS: Record<string, string> = {
    interior_pdf: "Interior PDF (KDP)",
    cover_pdf: "Cover PDF (KDP)",
    word: "Word Document (.docx)",
    markdown: "Markdown",
    text: "Plain Text",
  };

  return (
    <div className="rounded-xl bg-gray-800/50 border border-gray-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-gray-100">Export Files</h3>
        {!manifest && (
          <button
            onClick={load}
            disabled={loading}
            className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load Manifest"}
          </button>
        )}
      </div>
      {error && (
        <p className="text-sm text-red-400 mb-3">{error}</p>
      )}
      {manifest && (
        <div className="space-y-2">
          {Object.keys(manifest).map((artifact) => (
            <a
              key={artifact}
              href={api.exportUrl(bookId, artifact)}
              download
              className="flex items-center justify-between rounded-lg bg-gray-900 border border-gray-700 px-4 py-2.5 hover:border-indigo-500/50 transition-colors group"
            >
              <span className="text-sm text-gray-200">
                {ARTIFACT_LABELS[artifact] ?? artifact}
              </span>
              <span className="text-xs text-indigo-400 group-hover:text-indigo-300 transition-colors">
                Download ↓
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function BookDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const bookFetcher = useCallback(() => api.getBook(id), [id]);
  const versionsFetcher = useCallback(() => api.getVersions(id), [id]);

  const [book, bookLoading, bookError, refreshBook] = usePolling<Book>(
    bookFetcher,
    10000
  );
  const [versions, , , refreshVersions] = usePolling<StoryVersion[]>(
    versionsFetcher,
    10000
  );

  const { events, connected } = useBookStream(id);

  // Refresh book + versions whenever a status_change event arrives via WebSocket
  useEffect(() => {
    if (events.length > 0 && events[events.length - 1].type === "status_change") {
      refreshBook();
      refreshVersions();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length]);

  // Latest round's versions
  const latestRound =
    versions && versions.length > 0
      ? Math.max(...versions.map((v) => v.round))
      : 0;
  const latestVersions = (versions ?? []).filter(
    (v) => v.round === latestRound
  );

  // Best version by top judgement score
  const bestVersionId = latestVersions.reduce<string | null>((bestId, v) => {
    const score =
      v.judgements.length > 0
        ? Math.max(...v.judgements.map((j) => j.weighted_total))
        : -1;
    const bestScore =
      bestId != null
        ? Math.max(
            ...(latestVersions
              .find((lv) => lv.id === bestId)
              ?.judgements.map((j) => j.weighted_total) ?? [-1])
          )
        : -1;
    return score > bestScore ? v.id : bestId;
  }, null);

  const isApprovalGate = book?.status === "AWAITING_APPROVAL";
  const isExportReady = book?.status === "EXPORT_READY" || book?.status === "DONE";

  // Load metadata for export-ready books
  const metaFetcher = useCallback(
    () => (isExportReady ? api.getMetadata(id) : Promise.resolve(null)),
    [id, isExportReady]
  );
  const [metadata] = usePolling<BookMetadata | null>(metaFetcher, 30000);

  function handleApprovalAction() {
    refreshBook();
    refreshVersions();
  }

  if (bookLoading && !book) {
    return (
      <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
        <p className="text-gray-400 animate-pulse">Loading book…</p>
      </div>
    );
  }

  if (bookError && !book) {
    return (
      <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
        <p className="text-red-400">Error: {bookError}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0f1117]">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <Link
          href="/"
          className="text-gray-400 hover:text-gray-200 transition-colors text-sm"
        >
          ← Board
        </Link>
        <div className="h-4 w-px bg-gray-700" />
        <h1 className="text-base font-semibold text-gray-100 truncate flex-1">
          {book?.title ?? "Untitled Book"}
        </h1>
        {book && <StatusBadge status={book.status} />}
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-8">
        {/* Book meta */}
        {book && (
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            {[
              ["Status", STATUS_LABEL[book.status]],
              ["Round", `${book.current_round} / ${book.max_rounds}`],
              ["Threshold", book.score_threshold.toString()],
              ["Updated", new Date(book.updated_at).toLocaleString()],
            ].map(([label, val]) => (
              <div key={label} className="rounded-lg bg-gray-800/50 border border-gray-700 px-4 py-3">
                <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                <p className="text-sm font-medium text-gray-200">{val}</p>
              </div>
            ))}
          </div>
        )}

        {/* Approval gate */}
        {isApprovalGate && (
          <ApprovalGate bookId={id} onAction={handleApprovalAction} />
        )}

        {/* Story variants */}
        {latestVersions.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
              Round {latestRound} — {latestVersions.length} Variant
              {latestVersions.length !== 1 ? "s" : ""}
            </h2>
            <div className="space-y-5">
              {latestVersions
                .slice()
                .sort((a, b) => {
                  const scoreA =
                    a.judgements.length > 0
                      ? Math.max(...a.judgements.map((j) => j.weighted_total))
                      : -1;
                  const scoreB =
                    b.judgements.length > 0
                      ? Math.max(...b.judgements.map((j) => j.weighted_total))
                      : -1;
                  return scoreB - scoreA;
                })
                .map((v) => (
                  <VersionCard
                    key={v.id}
                    version={v}
                    bookId={id}
                    isBest={v.id === bestVersionId}
                  />
                ))}
            </div>
          </section>
        )}

        {/* Export-ready: metadata + download */}
        {isExportReady && (
          <>
            {metadata && (
              <MetadataPanel bookId={id} initialMeta={metadata} />
            )}
            <ExportPanel bookId={id} />
          </>
        )}

        {/* Live event feed */}
        <EventFeed events={events} connected={connected} />
      </main>
    </div>
  );
}
