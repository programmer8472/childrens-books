"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/hooks";
import { STATUS_LABEL, statusColor } from "@/lib/types";
import type { Book, BookStatus, StatusColor } from "@/lib/types";
import { NewBookModal } from "./NewBookModal";

const DOT: Record<StatusColor, string> = {
  green: "bg-green-400",
  yellow: "bg-amber-400 animate-pulse",
  blue: "bg-blue-400 animate-pulse",
  red: "bg-red-400",
  gray: "bg-gray-500",
};

type GroupKey = "needs" | "active" | "done" | "ended";

const GROUP_LABEL: Record<GroupKey, string> = {
  needs: "Needs you",
  active: "In progress",
  done: "Finished",
  ended: "Ended",
};

const GATE: BookStatus[] = ["AWAITING_SHORTLIST", "AWAITING_FINAL_APPROVAL", "AWAITING_APPROVAL"];

function group(b: Book): GroupKey {
  if (GATE.includes(b.status)) return "needs";
  if (b.status === "EXPORT_READY" || b.status === "DONE") return "done";
  if (b.status === "RETIRED" || b.status === "CANCELLED") return "ended";
  return "active";
}

function Row({ book, selected }: { book: Book; selected: boolean }) {
  const color = statusColor(book.status);
  return (
    <Link href={`/books/${book.id}`}>
      <div
        className={`flex items-center gap-3 rounded-lg px-3 py-2.5 cursor-pointer border transition-colors ${
          selected
            ? "bg-indigo-600/15 border-indigo-500/50"
            : "bg-transparent border-transparent hover:bg-gray-800/60"
        }`}
      >
        <span className={`h-2 w-2 rounded-full flex-shrink-0 ${DOT[color]}`} />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-gray-100 truncate leading-tight">
            {book.title ?? "Untitled Book"}
          </p>
          <p className="text-[11px] text-gray-500 truncate">
            {STATUS_LABEL[book.status]}
            {" · "}r{book.current_round}/{book.max_rounds}
          </p>
        </div>
      </div>
    </Link>
  );
}

export function BookList() {
  const pathname = usePathname();
  const selectedId = pathname?.startsWith("/books/") ? pathname.split("/")[2] : null;

  const fetcher = useCallback(() => api.listBooks(), []);
  const [books, loading, error, refresh] = usePolling<Book[]>(fetcher, 5000);
  const [showModal, setShowModal] = useState(false);

  const groups: Record<GroupKey, Book[]> = { needs: [], active: [], done: [], ended: [] };
  for (const b of books ?? []) groups[group(b)].push(b);
  const order: GroupKey[] = ["needs", "active", "done", "ended"];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-4 border-b border-gray-800 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-lg">📚</span>
          <span className="text-sm font-bold text-gray-100">Book Pipeline</span>
        </Link>
        <button
          onClick={() => setShowModal(true)}
          className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-500 transition-colors"
        >
          + New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {error && <p className="px-2 text-xs text-red-400">Failed to load: {error}</p>}
        {books && books.length === 0 && !loading && (
          <p className="px-2 text-xs text-gray-500 italic">No books yet — create one.</p>
        )}
        {order.map((key) =>
          groups[key].length === 0 ? null : (
            <div key={key}>
              <div className="flex items-center gap-2 px-2 mb-1">
                <h2 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  {GROUP_LABEL[key]}
                </h2>
                <span className="text-[10px] text-gray-600 font-mono">{groups[key].length}</span>
              </div>
              <div className="space-y-0.5">
                {groups[key].map((b) => (
                  <Row key={b.id} book={b} selected={b.id === selectedId} />
                ))}
              </div>
            </div>
          )
        )}
      </div>

      {showModal && (
        <NewBookModal
          onCreated={() => {
            setShowModal(false);
            refresh();
          }}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
