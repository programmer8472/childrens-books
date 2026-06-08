# Book Design Specification (Unit 8 law)

This is the **complete, binding design specification** for the compositor. Every number is justified by research against KDP requirements, industry standards, and Caldecott-level quality criteria. Nothing is negotiable downward. The goal is a book visually indistinguishable from — or better than — a Big Five traditionally published picture book.

---

## Canonical format

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Trim size | **8.5" × 8.5"** (square) | #1 format for ages 3–8 on KDP. Square maximises illustration area, reads as premium on Amazon thumbnails, comfortable for small hands. |
| Page count | **32 pages** | Industry standard. Libraries, bookstores, and parents recognise it as the proper picture book form. Divisible by 4 (KDP requirement); page 32 must be blank for barcode. |
| Spread count | **12 story spreads** (pages 5–28) | Leaves room for 4 pages front matter and 4 pages back matter. |
| Bleed | **0.125"** on all outside edges | KDP minimum. Compositor adds bleed automatically; safe content zone starts 0.375" inward from trim. |
| Final PDF page size (with bleed) | **8.75" × 8.75"** | 8.5 + 0.125 on each side = 8.75. This is what gets uploaded to KDP. |
| Resolution | **300 DPI minimum at print size** | KDP minimum. Compositor rejects images below this. Target 400 DPI for AI-generated illustrations. |
| Color space | **CMYK, U.S. Web Coated (SWOP) v2 ICC profile** | KDP auto-converts RGB but shifts saturated blues, greens, oranges. We convert ourselves with a proper ICC profile. |
| File format | **PDF/X-1a** for KDP upload | Embeds all fonts, flattens transparencies, embeds ICC profile. Only format guaranteed to print exactly as designed. |
| Gutter/inside margin | **0.5"** from spine | KDP minimum for 24–150 pages is 0.375"; we add 0.125" safety. No text or critical detail ever enters this zone. |

---

## Typography system

### Body text

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Font | **Andika** (SIL International, free OFL license) | Designed specifically for early literacy. Each letterform is maximally differentiated — no two characters share a confusable shape. Confirmed superior to OpenDyslexic in peer-reviewed 2024 research. |
| Size | **20pt** for ages 3–5; **18pt** for ages 5–8 | Industry standard is 16–22pt. We bias large because our primary market is ages 3–6. |
| Leading | **type size × 1.5** (30pt for 20pt type) | Research consensus: 1.4–1.6× gives young readers room to track lines. |
| Alignment | **Left-aligned** (ragged right) | Never justified. Justified text creates uneven word spacing that disrupts children's reading rhythm — the most common self-publisher mistake. |
| Color | **#1A1A1A on light; #FFFFFF on dark** | Near-black on warm white is easier on children's eyes than pure #000000 on coated paper. |
| Max characters per line | **35–45 characters** | 8–12 words. Long lines force small children to re-find their place. |
| Words per spread | Ages 3–5: **≤ 30 words**; Ages 5–8: **≤ 75 words** | 30 × 12 spreads = 360 words total — the ideal center of the 250–1,000 word picture book range. |

### Display / title font

| Parameter | Value |
|-----------|-------|
| Font | **Fredoka One** (free, Google Fonts) |
| Use | Book title, title pages only — never body text |
| Size | **28–36pt** depending on title length |
| Pairing rationale | Fredoka One and Andika share rounded, open letterforms without competing. Confirmed professional pairing by 2024 typography research. |

### Text contrast rules (enforced programmatically)

- Text overlaying an illustration: the pixel region behind text must have luminance delta ≥ 4.5:1 against text color (WCAG AA). If not, compositor renders a soft semi-transparent rounded pill behind the text — never a hard box (looks cheap).
- Dark illustrations get white text; light illustrations get near-black. The compositor measures the background automatically.
- Text is never placed inside the gutter zone (within 0.5" of spine) or outside the safe content zone.

---

## Spread layout system

A book with the same layout on every spread is boring. The compositor assigns a **spread type** based on narrative position. No self-published competitor does this — they use a single static template.

| Spread type | When used | Description |
|-------------|-----------|-------------|
| **FULL_BLEED_DOUBLE** | Climax, key emotional moment, opening | Illustration bleeds across both pages. Text placed in a clear area within the illustration. Maximum visual impact. |
| **FULL_BLEED_SINGLE_WITH_TEXT_PAGE** | Transitions, story establishment | Full-bleed illustration on one page; clean white facing page holds text. Elegant; preserves illustration without compromise. |
| **FULL_BLEED_SINGLE_OVERLAY** | Mid-story action, character dialogue | Full-bleed illustration fills one page; text overlays in a corner or bottom band with contrast treatment. |
| **PORTRAIT_WITH_CAPTION_BELOW** | Quieter moments, character introduction | Illustration in upper 65–70% of page; generous white space below holds text. Classic storybook look. |
| **VIGNETTE** | Transitions, internal monologue, humor beats | Illustration floats on white background without bleeding to edges. White space gives readers' eyes a rest. |

**Spread type assignment by narrative position** (orchestrator decides before images are generated; spread type is passed to the image provider via `params` so the illustration prompt is composed accordingly):

- Spread 1 (opening): `FULL_BLEED_DOUBLE`
- Spreads 2–4: `PORTRAIT_WITH_CAPTION_BELOW` or `FULL_BLEED_SINGLE_WITH_TEXT_PAGE`
- Spreads 5–8 (rising action): rotate `FULL_BLEED_SINGLE_OVERLAY` and `VIGNETTE`
- Spreads 9–10 (climax): `FULL_BLEED_DOUBLE`
- Spread 11 (resolution): `FULL_BLEED_SINGLE_WITH_TEXT_PAGE`
- Spread 12 (closing): `PORTRAIT_WITH_CAPTION_BELOW` or `VIGNETTE`

Spread type is stored per-page in the DB (`pages` table, `layout_type` column) so it is deterministic and previewable.

---

## Page structure (all 32 pages)

```
Page  1  — Half-title (title only, centered, Fredoka One 28pt)
Page  2  — Copyright + dedication (Andika 10pt, centered, generous leading)
Page  3  — Title page (full title, author, illustrator, Fredoka One)
Page  4  — Blank or full-bleed opening illustration (no text)
Pages 5–28 — 12 story spreads
Page 29  — About the author (author photo placeholder)
Page 30  — Series page / "Also by this author" (blank if first book)
Page 31  — Blank (required by KDP for expanded distribution)
Page 32  — Blank (KDP barcode page — MUST be blank)
```

---

## Color and print quality

- Illustrations must be CMYK before compositing. If the image provider returns RGB, the compositor converts with Pillow `ImageCms` and the SWOP v2 profile.
- Black text: **100% K only** (not rich black). Rich black on text causes fringing in print.
- White areas: **zero ink coverage** — never use a white fill that could convert to a faint CMYK tint.
- Final PDF file size target: **50–200 MB** (KDP limit is 650 MB).

---

## Cover specification

The cover is a separate PDF — a single flat file: back cover + spine + front cover, left to right.

| Parameter | Value |
|-----------|-------|
| Front cover size (with bleed) | **8.75" × 8.75"** |
| Spine width | `page_count × 0.002252"` (KDP formula for standard color paper) — 32 pages = **0.072"** |
| Back cover size (with bleed) | **8.75" × 8.75"** |
| Total flat width | `8.75 + spine + 8.75` = **17.572"** |
| Total flat height | **8.75"** |
| Resolution | **300 DPI minimum** |
| Barcode zone | Bottom-right of back cover, 2" × 1.2" cleared of any illustration detail |

Cover illustration is generated separately with a dedicated cover prompt. Must include: title (Fredoka One, large), author name (Andika, smaller), publisher imprint if any.

---

## Compositor architecture

```
app/compositor/
  __init__.py
  composer.py          — BookComposer: top-level, assembles all pages for a book_id
  spread_types.py      — SpreadType enum + layout geometry for each type
  page_renderer.py     — renders one page: places illustration + text, handles contrast
  cover_renderer.py    — renders the full flat cover PDF
  typography.py        — font loading, text measurement, line wrapping, contrast check
  color.py             — RGB→CMYK conversion, ICC profile management
  pdf_writer.py        — ReportLab-based PDF/X-1a assembly and export
  fake_compositor.py   — FakeComposer: valid-structure PDFs with placeholder content for tests
```

**Technology stack:**
- `reportlab` — PDF/X-1a generation with pixel-level layout control (Platypus `PageTemplate` + `Frame`)
- `Pillow` — Image resizing, DPI validation, RGB→CMYK with ICC profiles
- `fonttools` — Font subsetting and embedding verification
- All fonts (Andika, Fredoka One) bundled in `app/compositor/fonts/` — never rely on system fonts

**FakeComposer** generates structurally valid PDFs using colored rectangles in place of illustrations and lorem ipsum in the correct font/size. Every compositor test uses it. Real and fake compositor share the same interface.

---

## Why this beats the competition

Most self-published KDP children's books fail on at least three of these five axes. This pipeline addresses all five:

| Axis | Industry average | This pipeline |
|------|-----------------|---------------|
| **Typography** | Times New Roman or Arial at 14pt, justified, no leading control | Andika at 18–20pt, left-aligned, 1.5× leading — designed for child literacy |
| **Color accuracy** | RGB uploaded, KDP auto-converts, colors shift in print | CMYK at compositor time with SWOP v2 ICC profile; no surprises |
| **Layout variety** | One static template repeated on every spread | 5 spread types assigned by narrative position; pacing matches story arc |
| **Text safety** | Manual placement, often too close to gutter or trim | Programmatically enforced safe zones; contrast auto-checked at WCAG AA |
| **Print spec compliance** | Wrong DPI, missing bleed, wrong PDF version | 300 DPI enforced at ingest, 0.125" bleed added automatically, PDF/X-1a output |

The Caldecott criteria judge books on: technique, pictorial interpretation, style appropriateness, narrative communication, and child-centered presentation. Our typography and layout choices directly address the last two better than any self-published competitor.
