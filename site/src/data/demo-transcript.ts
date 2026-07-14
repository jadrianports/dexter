// site/src/data/demo-transcript.ts
//
// PLACEHOLDER CONTRACT — the `text` field of each dexter line must be replaced
// with VERBATIM, UNEDITED real Dexter output (PORT-02, sourced via a live bot).
// Do NOT "improve" a real line for punchiness — the legitimacy of the demo
// rests on the words being real. The `{{DEXTER_DEMO_LINE_*}}` tokens below are
// still the source of truth and are INTACT: PORT-02 is incomplete until a human
// swaps them for real lines.
//
// `previewSample` is a SEPARATE, explicitly-labeled placeholder shown ONLY while
// `text` still holds an unfilled `{{...}}` token, so the landing page renders as
// the finished component during development instead of leaking a raw token. It
// is design-preview scaffolding, not a claim of real output — the moment `text`
// is filled with a verbatim line, `previewSample` is bypassed and unused.
export const demoTranscript = [
  {
    speaker: "human",
    handle: "wrenlow",
    text: "dex, what do you think of my playlist?",
  },
  {
    speaker: "dexter",
    text: "{{DEXTER_DEMO_LINE_1}}", // verbatim /ask or /roast output — DO NOT AUTHOR
    previewSample: "Seventeen songs and four of them are the same sad boy. Bold curatorial vision.",
  },
  {
    speaker: "human",
    handle: "wrenlow",
    text: "playing this on repeat again lol",
  },
  {
    speaker: "dexter",
    text: "{{DEXTER_DEMO_LINE_2}}", // verbatim ambient/roast output — DO NOT AUTHOR
    previewSample: "Third time today. I'm keeping notes. For later.",
  },
] as const;

// Resolve to what the page should actually display: the real line if present,
// otherwise the labeled preview sample. A line still carrying a `{{...}}` token
// counts as unfilled.
export function resolveLine(entry: { text: string; previewSample?: string }): string {
  const unfilled = entry.text.includes("{{");
  return unfilled && entry.previewSample ? entry.previewSample : entry.text;
}
