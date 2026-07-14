// site/src/data/demo-transcript.ts
//
// PLACEHOLDER CONTRACT — DO NOT AUTHOR REPLACEMENT TEXT FOR dexterLine FIELDS.
// These two strings must be replaced with VERBATIM, UNEDITED real Dexter output
// sourced via 23-HUMAN-UAT.md (Finding 1 of 23-RESEARCH.md: logs/dexter.log does
// NOT contain usable output; the user supplies real lines). An executor or
// reviewer who "improves" these lines for punchiness breaks D-06's honesty
// premise — the whole legitimacy of this component rests on the words being real.
//
// STATUS: BLOCKED as of 2026-07-14 (see 23-DEMO-TRANSCRIPT.md). The user
// deferred supplying the two real Dexter lines. The tokens below are left
// VISIBLY INTACT on purpose — PORT-02 is incomplete until they are replaced.
// Do not fill them with plausible roasts, and do not substitute strings from
// personality/responses.py or personality/roasts.py (RESEARCH Finding 1 warns
// against exactly that substitution — those are template fallbacks, not
// Gemini generations, and using them would silently reopen the provenance
// question D-06 settled).
export const demoTranscript = [
  { speaker: "human", handle: "wrenlow", text: "dex what do you think of my playlist" },
  { speaker: "dexter", text: "{{DEXTER_DEMO_LINE_1}}" }, // verbatim /ask or /roast output — DO NOT AUTHOR
  { speaker: "human", handle: "wrenlow", text: "playing this on repeat again lol" },
  { speaker: "dexter", text: "{{DEXTER_DEMO_LINE_2}}" }, // verbatim ambient/roast output — DO NOT AUTHOR
];
