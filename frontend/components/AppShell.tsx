"use client";

import { BookList } from "./BookList";

/** Master/detail shell: a persistent book list on the left, detail on the right. */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col md:flex-row md:h-screen bg-[#0f1117]">
      <aside className="w-full md:w-80 md:flex-shrink-0 border-b md:border-b-0 md:border-r border-gray-800 md:h-screen">
        <BookList />
      </aside>
      <main className="flex-1 md:h-screen md:overflow-y-auto">{children}</main>
    </div>
  );
}
