"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";

interface Props {
  bookId: string;
  paragraphText: string;
  onClose: () => void;
}

export function ParagraphEditor({ bookId, paragraphText, onClose }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    original: string;
    rewritten: string;
  } | null>(null);

  async function handleRewrite() {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.rewriteParagraph(bookId, paragraphText, instruction.trim());
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rewrite failed");
    } finally {
      setLoading(false);
    }
  }

  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === overlayRef.current) onClose();
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={handleOverlayClick}
    >
      <div className="w-full max-w-2xl rounded-xl bg-gray-900 border border-gray-700 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 shrink-0">
          <h2 className="text-base font-semibold text-gray-100">
            Edit Paragraph
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-200 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-5 space-y-5">
          {/* Original */}
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
              Original
            </p>
            <p className="font-mono text-sm text-gray-300 bg-gray-800 rounded-lg p-4 leading-relaxed whitespace-pre-wrap">
              {paragraphText}
            </p>
          </div>

          {/* Instruction */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Instruction
            </label>
            <textarea
              className="w-full rounded-lg bg-gray-800 border border-gray-600 text-gray-100 text-sm px-3 py-2.5 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 resize-none h-20"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="e.g. Make it more exciting, use shorter sentences, add sensory details…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                  handleRewrite();
              }}
            />
            <p className="text-xs text-gray-600 mt-1">⌘↵ to rewrite</p>
          </div>

          {/* Error */}
          {error && (
            <p className="text-sm text-red-400 bg-red-950/50 rounded px-3 py-2">
              {error}
            </p>
          )}

          {/* Result */}
          {result && (
            <div>
              <p className="text-xs font-medium text-green-400 uppercase tracking-wider mb-2">
                Rewritten
              </p>
              <p className="font-mono text-sm text-gray-100 bg-gray-800 rounded-lg p-4 leading-relaxed whitespace-pre-wrap border border-green-800/50">
                {result.rewritten}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-700 flex justify-between items-center shrink-0">
          <button
            onClick={onClose}
            className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
          >
            Close
          </button>
          <div className="flex gap-3">
            {result && (
              <button
                onClick={() => setResult(null)}
                className="px-4 py-2 text-sm text-gray-300 hover:text-gray-100 border border-gray-600 rounded-lg hover:border-gray-500 transition-colors"
              >
                Try Again
              </button>
            )}
            <button
              onClick={handleRewrite}
              disabled={loading || !instruction.trim()}
              className="px-5 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors min-w-[100px]"
            >
              {loading ? (
                <span className="flex items-center gap-2 justify-center">
                  <span className="h-3 w-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Writing…
                </span>
              ) : result ? (
                "Rewrite Again"
              ) : (
                "Rewrite"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
