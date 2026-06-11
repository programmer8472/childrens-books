"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import {
  ADHD_CONCEPTS,
  LOCKED_THEME,
  randomAdhdConcept,
  type AdhdConcept,
} from "@/lib/adhdLibrary";

interface Props {
  onCreated: () => void;
  onClose: () => void;
}

export function NewBookModal({ onCreated, onClose }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Start from one coherent concept so the title, characters, setting, and
  // description all describe the same child. Picking/shuffling swaps the whole
  // concept; editing any single field marks the idea "custom" but keeps the
  // rest intact.
  const [concept] = useState(randomAdhdConcept);
  const [conceptId, setConceptId] = useState(concept.id);
  const [title, setTitle] = useState(concept.title);
  const [description, setDescription] = useState(concept.description);
  const [characters, setCharacters] = useState(concept.characters);
  const [setting, setSetting] = useState(concept.setting);
  const [ageRange, setAgeRange] = useState("4-8");
  const [maxRounds, setMaxRounds] = useState(5);
  const [threshold, setThreshold] = useState(7.5);

  function applyConcept(c: AdhdConcept) {
    setConceptId(c.id);
    setTitle(c.title);
    setDescription(c.description);
    setCharacters(c.characters);
    setSetting(c.setting);
  }

  // Editing any field on its own breaks the 1:1 link to a concept, so we mark
  // the idea custom while leaving the other fields as they are.
  function editTitle(v: string) { setTitle(v); setConceptId(""); }
  function editDescription(v: string) { setDescription(v); setConceptId(""); }
  function editCharacters(v: string) { setCharacters(v); setConceptId(""); }
  function editSetting(v: string) { setSetting(v); setConceptId(""); }

  function shuffleAll() {
    applyConcept(randomAdhdConcept());
  }

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
          theme: LOCKED_THEME,
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
      <div className="w-full max-w-lg rounded-xl bg-gray-900 border border-gray-700 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 sticky top-0 bg-gray-900 z-10">
          <h2 className="text-lg font-semibold text-gray-100">New Book</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-200 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          {/* Locked theme + shuffle */}
          <div className="flex items-center justify-between gap-3 rounded-lg bg-indigo-950/40 border border-indigo-800/60 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-indigo-300">Theme</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600/30 border border-indigo-500/50 px-2 py-0.5 text-xs font-semibold text-indigo-200">
                🔒 {LOCKED_THEME}
              </span>
            </div>
            <button
              type="button"
              onClick={shuffleAll}
              className="text-xs text-indigo-300 hover:text-indigo-100 transition-colors px-2 py-1 rounded hover:bg-indigo-900/40"
            >
              🎲 Shuffle idea
            </button>
          </div>

          {/* Coherent story-idea picker — loads a whole concept at once */}
          <Field label="Story idea">
            <select
              className={input}
              value={conceptId}
              onChange={(e) => {
                const c = ADHD_CONCEPTS.find((x) => x.id === e.target.value);
                if (c) applyConcept(c);
              }}
            >
              {conceptId === "" && (
                <option value="">Custom ✎ — edited from a story idea</option>
              )}
              {ADHD_CONCEPTS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-gray-500">
              Pick a complete idea — the title, characters, setting, and story
              stay about the same child. Edit any field below to fine-tune.
            </p>
          </Field>

          <Field label="Working Title *">
            <input
              className={input}
              value={title}
              onChange={(e) => editTitle(e.target.value)}
              required
            />
          </Field>

          <Field label="Story Description *">
            <textarea
              className={`${input} h-24 resize-none`}
              value={description}
              onChange={(e) => editDescription(e.target.value)}
              required
            />
          </Field>

          <Field label="Main Characters">
            <input
              className={input}
              value={characters}
              onChange={(e) => editCharacters(e.target.value)}
            />
          </Field>

          <Field label="Setting">
            <input
              className={input}
              value={setting}
              onChange={(e) => editSetting(e.target.value)}
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
            <Field label="Theme">
              <input className={`${input} opacity-70`} value={LOCKED_THEME} disabled />
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
