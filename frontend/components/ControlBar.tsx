"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Book, BookStatus } from "@/lib/types";

const TERMINAL: BookStatus[] = ["EXPORT_READY", "DONE", "RETIRED", "CANCELLED"];
const RETRYABLE: BookStatus[] = ["JUDGING", "REVISION"];

export function ControlBar({ book, onChanged }: { book: Book; onChanged: () => void }) {
  const [busy, setBusy] = useState<null | "cancel" | "retry">(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cancellable = !TERMINAL.includes(book.status);
  const retryable = RETRYABLE.includes(book.status);
  const cancelling = book.cancel_requested && cancellable;

  async function doCancel() {
    setBusy("cancel");
    setError(null);
    try {
      await api.cancelBook(book.id);
      setConfirming(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
    } finally {
      setBusy(null);
    }
  }

  async function doRetry() {
    setBusy("retry");
    setError(null);
    try {
      await api.retryBook(book.id);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setBusy(null);
    }
  }

  if (!cancellable && !retryable) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {retryable && (
        <button
          onClick={doRetry}
          disabled={busy !== null}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-700 text-gray-200 hover:bg-gray-600 disabled:opacity-50 transition-colors"
        >
          {busy === "retry" ? "Retrying…" : "↻ Retry stage"}
        </button>
      )}

      {cancellable &&
        (cancelling ? (
          <span className="px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-700/60 text-gray-400 border border-gray-600">
            Cancelling…
          </span>
        ) : confirming ? (
          <span className="flex items-center gap-2">
            <span className="text-xs text-gray-400">Cancel this run?</span>
            <button
              onClick={doCancel}
              disabled={busy !== null}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-600 text-white hover:bg-red-500 disabled:opacity-50 transition-colors"
            >
              {busy === "cancel" ? "Cancelling…" : "Yes, cancel"}
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="px-3 py-1.5 rounded-lg text-xs text-gray-300 hover:text-gray-100"
            >
              Keep running
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-red-500/40 text-red-300 hover:bg-red-500/10 transition-colors"
          >
            ✕ Cancel run
          </button>
        ))}

      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  );
}
