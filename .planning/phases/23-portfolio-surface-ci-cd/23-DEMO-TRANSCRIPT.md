# Demo Transcript — Verbatim Dexter Output (D-06)

**Status: `BLOCKED` — real lines not yet supplied (deferred by user 2026-07-14).**

This file is the byte-for-byte source of truth for `site/src/data/demo-transcript.ts`
(plan 23-06) and, transitively, `docs/demo.gif` (plan 23-07).

## The honesty rule (D-06)

The demo mock reconstructs a Discord conversation in HTML/CSS. Reconstructing the **pixels**
is a normal documentation convention. The **words Dexter says must be real** — actual,
unedited Dexter output copied *verbatim* from a live Discord session. They must NOT be
authored, edited, tightened, re-punctuated, or substituted with strings from
`personality/responses.py` / `personality/roasts.py`. A line that is a bit flat is honest;
a perfect invented line is a fabrication on a page whose entire thesis is honest disclosure.

**Downstream rule:** whoever wires plan 23-06 must copy these lines byte-for-byte. Do not
edit them. If the tokens below are still present, PORT-02 is **incomplete**, not merely
unstyled.

## Human scaffolding (author-able — NOT attributed to Dexter)

Fictional human handle: `wrenlow`. The two human setup lines below are ours to author and
may be adapted to fit whatever real Dexter lines land here:

- **Setup 1 (human):** "dex what do you think of my playlist"
- **Setup 2 (human):** "playing this on repeat again lol"

## Dexter's lines (GATED — must be verbatim real output)

### Line 1 — pairs with Setup 1
- **Surface:** _{{TBD — /ask or /roast reacting to taste/history}}_
- **Rough date:** _{{TBD}}_
- **Verbatim text:**

```
{{DEXTER_DEMO_LINE_1}}
```

### Line 2 — pairs with Setup 2
- **Surface:** _{{TBD — ambient roast or repeat-song roast}}_
- **Rough date:** _{{TBD}}_
- **Verbatim text:**

```
{{DEXTER_DEMO_LINE_2}}
```

## Provenance

These lines, once supplied, are **user-supplied verbatim Dexter output** and must not be
edited downstream. Until the `{{DEXTER_DEMO_LINE_*}}` tokens are replaced with real,
copy-pasted Dexter output, this deliverable is `BLOCKED` and PORT-02 is incomplete.
Deferred by the user on 2026-07-14; carried into `23-HUMAN-UAT.md` at phase close.
