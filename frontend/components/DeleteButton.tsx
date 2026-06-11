"use client";

import { useState } from "react";
import { api } from "@/lib/api";

/**
 * Delete control with an inline confirm step (matching ControlBar's pattern).
 * Used in the book detail header. `onDeleted` runs after a successful delete —
 * typically navigate away from the now-gone book.
 */
export function DeleteButton({
  bookId,
  onDeleted,
}: {
  bookId: string;
  onDeleted: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function doDelete() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteBook(bookId);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
      setBusy(false);
    }
  }

  if (confirming) {
    return (
      <span className="flex items-center gap-2">
        <span className="text-xs text-gray-400">Delete permanently?</span>
        <button
          onClick={doDelete}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-600 text-white hover:bg-red-500 disabled:opacity-50 transition-colors"
        >
          {busy ? "Deleting…" : "Yes, delete"}
        </button>
        <button
          onClick={() => setConfirming(false)}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-xs text-gray-300 hover:text-gray-100"
        >
          Keep
        </button>
        {error && <span className="text-xs text-red-400">{error}</span>}
      </span>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="px-3 py-1.5 rounded-lg text-xs font-medium border border-red-500/40 text-red-300 hover:bg-red-500/10 transition-colors"
    >
      🗑 Delete
    </button>
  );
}
