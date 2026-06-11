"use client";

import { RUNNING_STATUSES, STATUS_LABEL, statusColor } from "@/lib/types";
import type { BookStatus } from "@/lib/types";

const COLOR_CLASSES = {
  green: {
    badge: "bg-green-900/50 text-green-300 border border-green-700",
    dot: "bg-green-400",
  },
  yellow: {
    badge: "bg-yellow-900/50 text-yellow-300 border border-yellow-700",
    dot: "bg-yellow-400 animate-pulse",
  },
  blue: {
    badge: "bg-blue-900/50 text-blue-300 border border-blue-700",
    dot: "bg-blue-400 animate-pulse",
  },
  red: {
    badge: "bg-red-900/50 text-red-300 border border-red-700",
    dot: "bg-red-400",
  },
  gray: {
    badge: "bg-gray-700/50 text-gray-300 border border-gray-600",
    dot: "bg-gray-400",
  },
} as const;

export function StatusBadge({ status }: { status: BookStatus }) {
  const color = statusColor(status);
  const cls = COLOR_CLASSES[color];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${cls.badge}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${cls.dot}`} />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function statusBorderColor(status: BookStatus): string {
  const c = statusColor(status);
  return {
    green: "border-l-green-500",
    yellow: "border-l-yellow-500",
    blue: "border-l-blue-500",
    red: "border-l-red-500",
    gray: "border-l-gray-500",
  }[c];
}

export function isRunning(status: BookStatus): boolean {
  return (RUNNING_STATUSES as string[]).includes(status);
}
