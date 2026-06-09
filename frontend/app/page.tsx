"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/hooks";
import type { Book } from "@/lib/types";
import { BookCard } from "@/components/BookCard";
import { NewBookModal } from "@/components/NewBookModal";
import { StatusBadge } from "@/components/StatusBadge";
import Link from "next/link";

function PriorityQueue({ books }: { books: Book[] }) {
  const pending = books.filter((b) => b.status === "AWAITING_APPROVAL");
  if (pending.length === 0) return null;

  return (
    <section className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
        <h2 className="text-sm font-semibold text-blue-300 uppercase tracking-wider">
          Needs Your Approval — {pending.length}
        </h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {pending.map((book) => (
          <Link key={book.id} href={`/books/${book.id}`}>
            <div className="rounded-lg border-2 border-blue-500/60 bg-blue-950/30 p-4 hover:border-blue-400 transition-colors cursor-pointer shadow-lg shadow-blue-950/20">
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-semibold text-gray-100 truncate">
                  {book.title ?? "Untitled Book"}
                </h3>
                <StatusBadge status={book.status} />
              </div>
              <p className="text-xs text-blue-300">
                Round {book.current_round}/{book.max_rounds} — click to review
                &amp; approve
              </p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

type GroupKey = "running" | "waiting" | "complete" | "retired";

const GROUP_ORDER: GroupKey[] = ["running", "waiting", "complete", "retired"];

const GROUP_LABEL: Record<GroupKey, string> = {
  running: "In Progress",
  waiting: "Draft / Starting",
  complete: "Completed",
  retired: "Retired",
};

function groupBook(book: Book): GroupKey {
  const s = book.status;
  if (
    [
      "OUTLINING",
      "WRITING",
      "JUDGING",
      "REVISION",
      "GENERATING_IMAGES",
      "GENERATING_COVER",
      "DRAFTING_METADATA",
      "EXPORTING",
    ].includes(s)
  )
    return "running";
  if (s === "RETIRED") return "retired";
  if (["EXPORT_READY", "DONE", "APPROVED"].includes(s)) return "complete";
  return "waiting";
}

export default function HomePage() {
  const [showModal, setShowModal] = useState(false);

  const fetcher = useCallback(() => api.listBooks(), []);
  const [books, loading, error, refresh] = usePolling<Book[]>(fetcher, 8000);

  const booksExcludingApproval = (books ?? []).filter(
    (b) => b.status !== "AWAITING_APPROVAL"
  );

  const groups: Record<GroupKey, Book[]> = {
    running: [],
    waiting: [],
    complete: [],
    retired: [],
  };
  for (const b of booksExcludingApproval) {
    groups[groupBook(b)].push(b);
  }

  function handleCreated() {
    setShowModal(false);
    refresh();
  }

  return (
    <div className="min-h-screen bg-[#0f1117]">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-gray-100">📚</span>
          <h1 className="text-lg font-bold text-gray-100">Book Pipeline</h1>
          {loading && (
            <span className="text-xs text-gray-500 animate-pulse">
              loading…
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={refresh}
            className="text-xs text-gray-400 hover:text-gray-200 transition-colors px-2 py-1 rounded hover:bg-gray-800"
          >
            ↺ Refresh
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 transition-colors"
          >
            <span className="text-base leading-none">+</span> New Book
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 rounded-lg bg-red-950/50 border border-red-800 px-4 py-3 text-sm text-red-300">
            Failed to load books: {error}
          </div>
        )}

        {/* Priority queue */}
        {books && <PriorityQueue books={books} />}

        {/* Kanban columns */}
        {books && books.length > 0 && (
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {GROUP_ORDER.map((key) => {
              const group = groups[key];
              return (
                <div key={key}>
                  <div className="flex items-center gap-2 mb-3">
                    <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                      {GROUP_LABEL[key]}
                    </h2>
                    {group.length > 0 && (
                      <span className="rounded-full bg-gray-800 text-gray-400 text-xs px-1.5 py-0.5 font-mono">
                        {group.length}
                      </span>
                    )}
                  </div>
                  <div className="space-y-2">
                    {group.length === 0 && (
                      <p className="text-xs text-gray-600 italic px-1">
                        Empty
                      </p>
                    )}
                    {group.map((book) => (
                      <BookCard key={book.id} book={book} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {books && books.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <p className="text-4xl mb-4">📖</p>
            <p className="text-gray-300 font-medium mb-1">No books yet</p>
            <p className="text-sm text-gray-500 mb-6">
              Create your first book to start the pipeline.
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 transition-colors"
            >
              Create a Book
            </button>
          </div>
        )}
      </main>

      {showModal && (
        <NewBookModal
          onCreated={handleCreated}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
