"use client";

import Link from "next/link";
import type { Book } from "@/lib/types";
import { StatusBadge, statusBorderColor } from "./StatusBadge";

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function BookCard({ book }: { book: Book }) {
  const border = statusBorderColor(book.status);
  const displayTitle = book.title ?? "Untitled Book";

  return (
    <Link href={`/books/${book.id}`}>
      <div
        className={`group relative rounded-lg bg-gray-800 border-l-4 ${border} border border-gray-700 p-4 hover:bg-gray-750 hover:border-gray-600 transition-colors cursor-pointer`}
      >
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium text-gray-100 truncate text-sm leading-5">
            {displayTitle}
          </h3>
          <StatusBadge status={book.status} />
        </div>

        <div className="mt-2 flex items-center gap-3 text-xs text-gray-400">
          <span>Round {book.current_round}/{book.max_rounds}</span>
          <span>·</span>
          <span>Threshold {book.score_threshold}</span>
          <span>·</span>
          <span>{timeAgo(book.updated_at)}</span>
        </div>
      </div>
    </Link>
  );
}
