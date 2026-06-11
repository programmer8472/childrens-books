import type {
  Book,
  BookMetadata,
  CreateBookPayload,
  PreviewInfo,
  StoryVersion,
} from "./types";

const BASE =
  typeof window === "undefined"
    ? (process.env.API_URL ?? "http://localhost:8001")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001");

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Books
  listBooks: () => req<Book[]>("/books"),
  getBook: (id: string) => req<Book>(`/books/${id}`),
  createBook: (body: CreateBookPayload) =>
    req<Book>("/books", { method: "POST", body: JSON.stringify(body) }),

  // Pipeline actions
  approveBook: (id: string, story_version_id?: string) =>
    req<{ ok: boolean; status: string }>(`/books/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ story_version_id: story_version_id ?? null }),
    }),
  rejectBook: (id: string, note?: string) =>
    req<{ ok: boolean; status: string }>(`/books/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  retryBook: (id: string) =>
    req<{ ok: boolean }>(`/books/${id}/retry`, { method: "POST" }),
  cancelBook: (id: string) =>
    req<{ ok: boolean; status: string; cancelling?: boolean }>(
      `/books/${id}/cancel`,
      { method: "POST" }
    ),
  shortlistVersions: (id: string, story_version_ids: string[]) =>
    req<{ ok: boolean; status: string }>(`/books/${id}/shortlist`, {
      method: "POST",
      body: JSON.stringify({ story_version_ids }),
    }),

  // Versions
  getVersions: (id: string) =>
    req<StoryVersion[]>(`/books/${id}/versions`),

  // Metadata
  getMetadata: (id: string) => req<BookMetadata>(`/books/${id}/metadata`),
  updateMetadata: (id: string, body: Partial<BookMetadata>) =>
    req<BookMetadata>(`/books/${id}/metadata`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // Inline editor
  rewriteParagraph: (
    id: string,
    paragraph_text: string,
    instruction: string
  ) =>
    req<{ original: string; rewritten: string }>(
      `/books/${id}/paragraphs/rewrite`,
      { method: "POST", body: JSON.stringify({ paragraph_text, instruction }) }
    ),

  // Export
  getExportManifest: (id: string) =>
    req<Record<string, string>>(`/books/${id}/export`),
  exportUrl: (id: string, artifact: string) =>
    `${BASE}/books/${id}/export/${artifact}`,

  // Visual QA previews
  getPreviews: (id: string) =>
    req<PreviewInfo>(`/books/${id}/previews`),
  previewUrl: (id: string, index: number) =>
    `${BASE}/books/${id}/previews/${index}`,
};
