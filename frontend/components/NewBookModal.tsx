"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";

interface Props {
  onCreated: () => void;
  onClose: () => void;
}

export function NewBookModal({ onCreated, onClose }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [characters, setCharacters] = useState("");
  const [setting, setSetting] = useState("");
  const [ageRange, setAgeRange] = useState("4-8");
  const [theme, setTheme] = useState("");
  const [maxRounds, setMaxRounds] = useState(5);
  const [threshold, setThreshold] = useState(7.5);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !description.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createBook({
        title: title.trim(),
        brief: {
          description: description.trim(),
          characters: characters.trim(),
          setting: setting.trim(),
          age_range: ageRange,
          theme: theme.trim() || undefined,
        },
        max_rounds: maxRounds,
        score_threshold: threshold,
      });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create book");
      setSubmitting(false);
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
      <div className="w-full max-w-lg rounded-xl bg-gray-900 border border-gray-700 shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-gray-100">New Book</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-200 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          <Field label="Working Title *">
            <input
              className={input}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="The Little Star Who Was Afraid of the Dark"
              required
            />
          </Field>

          <Field label="Story Description *">
            <textarea
              className={`${input} h-24 resize-none`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="A brief description of the plot and emotional arc…"
              required
            />
          </Field>

          <Field label="Main Characters">
            <input
              className={input}
              value={characters}
              onChange={(e) => setCharacters(e.target.value)}
              placeholder="Mia (brave 6-year-old girl), Luma (her stuffed rabbit)"
            />
          </Field>

          <Field label="Setting">
            <input
              className={input}
              value={setting}
              onChange={(e) => setSetting(e.target.value)}
              placeholder="A cozy suburban neighborhood, a magical forest nearby"
            />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Target Age Range">
              <select
                className={input}
                value={ageRange}
                onChange={(e) => setAgeRange(e.target.value)}
              >
                <option value="2-4">2–4 (Board book)</option>
                <option value="4-8">4–8 (Picture book)</option>
                <option value="6-10">6–10 (Early reader)</option>
                <option value="8-12">8–12 (Middle grade)</option>
              </select>
            </Field>

            <Field label="Theme / Genre">
              <input
                className={input}
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
                placeholder="Courage, friendship"
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field label={`Max Rounds (${maxRounds})`}>
              <input
                type="range"
                min={1}
                max={10}
                value={maxRounds}
                onChange={(e) => setMaxRounds(Number(e.target.value))}
                className="w-full accent-indigo-500 mt-2"
              />
            </Field>
            <Field label={`Score Threshold (${threshold})`}>
              <input
                type="range"
                min={5}
                max={10}
                step={0.5}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full accent-indigo-500 mt-2"
              />
            </Field>
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-950/50 rounded px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-300 hover:text-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Creating…" : "Create Book"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const input =
  "w-full rounded-md bg-gray-800 border border-gray-600 text-gray-100 text-sm px-3 py-2 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-400 mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}
