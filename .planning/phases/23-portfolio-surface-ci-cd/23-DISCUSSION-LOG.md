# Phase 23: Portfolio Surface & CI/CD - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-14
**Phase:** 23-portfolio-surface-ci-cd
**Areas discussed:** Landing page shape, Demo GIF (PORT-02), README + honest disclosure, CI/CD wiring, Sequencing & extras

---

## Landing page shape

### Q1 — How should the /site landing page be built?

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-rolled static HTML/CSS **(Claude's rec)** | Zero build step, zero new deps, zero new toolchain in a Python repo | |
| Single-file HTML (everything inline) | Minimal, but unreviewable diffs | |
| Static site generator (Astro / 11ty) | Nicer authoring; costs a Node toolchain and diverges dist/ from the scanned source | ✓ |

**User's choice:** Static site generator — **overriding Claude's recommendation.**
**Notes:** Claude immediately flagged the consequence rather than proceeding: an SSG breaks Phase 22's
drift guard by construction, because the guard is a static text scan over git-tracked `.md`/`.html`/`.txt`
files, and an SSG commits `.astro` templates while its `dist/` is built in CI and never committed. The
guard would scan nothing and pass vacuously forever. This became the next question.

### Q2 — How do we keep the drift guard real under an SSG?

| Option | Description | Selected |
|--------|-------------|----------|
| Generated `invite-url.txt` as single source **(Claude's rec)** | A `.txt` already in the guard's allowlist; existing test enforces it with zero guard changes; keeps the gate inside plain `pytest` | |
| Widen the allowlist to cover templates | Smallest diff; only guards a LITERAL string — goes blind if the template builds the URL from a variable | |
| Build the site in CI, scan the built output | Guards the exact artifact shipped to Pages regardless of how the URL is produced; CI-only, needs a Node build first | ✓ |

**User's choice:** Build the site in CI, scan `dist/*.html`.
**Notes:** User asked a follow-up mid-selection — *"but it'd still be in ci.yml right? or another workflow?"* —
which produced the topology decision (D-03): the **scan** goes in `ci.yml` (unprivileged gate, runs on
push AND PR, needs only the existing `contents: read`), while the **Pages deploy** goes in its own
`pages.yml` (needs `pages: write` + `id-token: write`, main-push only). Splitting them keeps an
elevated-permission job out of the PR-triggered workflow, preserving Phase 18's T-18-CIPRIV discipline.
Accepted cost: the site builds twice.

### Q3 — Which static site generator?

| Option | Description | Selected |
|--------|-------------|----------|
| Astro **(Claude's rec)** | Zero JS by default → dist/ is essentially plain static HTML, keeping the scan simple and the artifact small; strong asset handling; HTML-shaped components | ✓ |
| Eleventy (11ty) | Lighter Node footprint; weaker asset pipeline, less familiar templates | |
| You decide | Planner picks based on research | |

**User's choice:** Astro.

### Q4 — Visual direction?

| Option | Description | Selected |
|--------|-------------|----------|
| Dark, terminal-ish, in Dexter's voice **(Claude's rec)** | The page IS the personality demo; sarcasm in the copy, never in the structure | ✓ |
| Clean, neutral, recruiter-safe | Professional but actively hides the differentiator | |
| Discord-native styling | Instantly legible; reads as derivative, edges toward implying affiliation | |

**User's choice:** Dark/terminal, in Dexter's voice.

### Q5 — Page scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Single scroll: hero → demo → features → honest boundaries → CTA **(Claude's rec)** | Demo lands high (show then tell); PORT-04 gets a real section before the CTA; architecture links to the README rather than duplicating it | ✓ |
| Same, plus an on-page architecture section | Recruiter never leaves; duplicates PORT-03 on a second surface that can drift | |
| Multi-page site | Over-built; more places for the link and disclosures to fall out of sync | |

**User's choice:** Single scroll.

---

## Demo GIF (PORT-02)

### Q1 — What format is the embedded demo?

| Option | Description | Selected |
|--------|-------------|----------|
| Recorded .webm/.mp4, autoplay-loop-muted **(Claude's rec)** | Looks like a GIF, 10–20× smaller | ✓ *(later reversed)* |
| A real .gif | Literal PORT-02 compliance; multi-MB binary, worse quality, slower page | |
| Styled HTML/CSS mock transcript | Zero capture, zero binary; but a mockup presented as a demo | |

**User's choice (initially):** Recorded .webm — **later reversed, see Q3.**

### Q2 — What ships if the real capture isn't done in time?

| Option | Description | Selected |
|--------|-------------|----------|
| Ship the slot + placeholder; real capture as HUMAN-UAT **(Claude's rec)** | Page structurally complete, CI/Pages provably green; one-file drop-in later | ✓ *(later moot)* |
| Phase blocks on the real recording | Cleanest bookkeeping; blocks the milestone on a live session | |
| Ship without a demo | Fails PORT-02 outright | |

**User's choice:** Ship slot + placeholder.
**Notes:** User first pushed back with *"how am i suppose to demo it? what do i show? arent gifs suppose
to be short?"* — Claude supplied a concrete 12–18s three-beat shot list (`/roast @user` as the
deterministic money shot, `/play` for the now-playing embed + control buttons, optional `/ask`; plus the
100%-deterministic repeat-song roast as an alternative), the capture tooling (Game Bar / ShareX), and a
ready-made ffmpeg conversion command.

### Q3 — Can Claude produce the demo itself?

**User asked:** *"btw is there any way you can make the gif yourself to demo at all? research"*
**Claude's answer:** No, for a real recording — two blockers. Technical: no ability to screen-record the
user's machine or drive their Discord desktop client. **Policy: the obvious workaround (pointing Playwright
at `discord.com/app` and logging in as the user) is automating a Discord user account, which Discord's ToS
explicitly prohibits (the self-bot rule).** Claude declined it and would not recommend a portfolio piece
whose demo was captured by violating platform terms. Claude offered instead to reduce the user's part to
~1 minute (a `scripts/make-demo.sh`, a shot list, and a pre-built placeholder + poster frame).

### Q4 — REVERSAL: staged HTML mockup after all?

**User's push-back:** *"staged html mockup can work actually, given there is already a CTA there to try
the bot out for themselves."*
**Claude's response:** Conceded that the earlier objection was overstated. A stylized HTML reproduction of
a UI is a normal, honest convention — what makes a mock dishonest is if **the words are ours**. Established
the honesty rule that makes it legitimate: **the transcript must be verbatim real Dexter output** (real
words, reconstructed pixels; the page never claims to be a recording). Also surfaced that an HTML mock
**flips the earlier "can you make it yourself" answer to yes** — Playwright can render the mock page and
produce the README's GIF end-to-end, with no capture session at all. Stated the two costs plainly: PORT-02's
literal "GIF of a recording" wording is not met (intent is, letter isn't — a recorded reinterpretation), and
the mock can't convincingly show the Phase 7 now-playing embed + control buttons.

| Option | Description | Selected |
|--------|-------------|----------|
| HTML/CSS mock, real verbatim Dexter output **(Claude's rec)** | Zero recording session; Claude renders the README GIF via Playwright; honest because the words are genuine; unblocks the phase completely | ✓ |
| Mock now, real recording swaps in later | Best of both over time; two implementations, and the "later" swap often never happens | |
| Real recording after all | Highest fidelity, shows the player UI, satisfies PORT-02 literally; blocks on a live session | |

**User's choice:** HTML/CSS mock with verbatim real Dexter output. **This supersedes Q1 and Q2.**
**Notes:** Claude flagged a lead for the researcher — `logs/dexter.log` may already contain real generated
Dexter responses, which would make even the "paste a few real lines" step unnecessary and PORT-02 fully
self-contained.

---

## README + honest disclosure

### Q1 — Does the demo appear in the README too?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — a small separate .gif for the README only **(Claude's rec)** | GitHub markdown doesn't reliably autoplay a relative `<video>`; one recording → two derivatives | ✓ |
| Yes — a static screenshot linking to the site | Tiny, always renders; a still can't show comedic timing | |
| No — README links to the page | Zero binary weight; the most persuasive artifact is one click away from where engineers land | |

**User's choice:** Separate README .gif.
**Notes:** Under the D-06 reversal this GIF is rendered from the HTML mock via Playwright, and it
incidentally satisfies PORT-02's literal "GIF" wording — though the *provenance* is a mock, which CONTEXT.md
records rather than obscures.

### Q2 — How deep does the case study go?

| Option | Description | Selected |
|--------|-------------|----------|
| Mid-depth: architecture summary + one mermaid diagram + 3–4 "hard problem" callouts **(Claude's rec)** | What a senior engineer skims in 90 seconds and is impressed by | ✓ |
| Deep: full per-subsystem case study | Most complete; nobody reads a 900-line README and the good parts get buried | |
| Shallow: tagline, features, badges, invite, boundaries | Fast; fails PORT-03's explicit "architecture case study" ask | |

**User's choice:** Mid-depth.

### Q3 — Whose voice is the README in?

| Option | Description | Selected |
|--------|-------------|----------|
| Professional engineering prose, with Dexter quoted **(Claude's rec)** | Recruiters need to see you can write an architecture doc; personality lives on the landing page and in quoted output | ✓ |
| Fully in Dexter's lowercase voice | Distinctive; makes the engineering hard to evaluate and turns PORT-04's disclosure into a joke | |
| Professional throughout, no personality at all | Safest; the README of a personality bot never shows the personality | |

**User's choice:** Professional prose, Dexter quoted.

### Q4 — Where do the four honest boundaries live?

| Option | Description | Selected |
|--------|-------------|----------|
| Both surfaces, framed as engineering tradeoffs **(Claude's rec)** | Constraint → deliberate decision; the hosting caveat sits BEFORE the CTA so nobody invites an offline bot unknowingly | ✓ |
| README only; landing page stays a pitch | Clean page; recreates the exact bad experience PORT-04 exists to prevent | |
| Both surfaces, stated plainly as limitations | Totally honest; reads as a list of things wrong with the project rather than deliberate judgment | |

**User's choice:** Both surfaces, tradeoff framing.

---

## CI/CD wiring

### Q1 — How does Pages publish (CICD-02)?

| Option | Description | Selected |
|--------|-------------|----------|
| `actions/deploy-pages` with an artifact **(Claude's rec)** | Official path; narrow `pages: write` + `id-token: write` scoped to one job; no build output ever committed | ✓ |
| Push built output to a gh-pages branch | Widely used; a second branch of generated files, broader token, junk commits | |

**User's choice:** `actions/deploy-pages`.

### Q2 — Is the Pages deploy gated on CI passing?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — deploy only after the test+lint+drift gate is green **(Claude's rec)** | A broken drift guard must never publish a page with a wrong invite URL | ✓ |
| No — deploy on every push to main | Simpler; makes the drift guard advisory rather than enforcing | |

**User's choice:** Gated on green.

### Q3 — GHCR trigger + architectures (CICD-03)?

| Option | Description | Selected |
|--------|-------------|----------|
| Git tag `v*` → amd64 + arm64 **(Claude's rec)** | The parked future host is most plausibly an ARM Pi; amd64-only would be unpullable on the exact machine CICD-03 serves | ✓ |
| Git tag `v*` → amd64 only | Faster build; breaks the "zero build step" promise on ARM | |
| GitHub Release published → multi-arch | Tidier; this repo tags milestones without cutting Releases, so it'd be a new habit that may not stick | |

**User's choice:** `v*` tag, multi-arch.

### Q4 — GHCR package visibility?

| Option | Description | Selected |
|--------|-------------|----------|
| Ship it, flip the package public by hand — HUMAN-UAT item **(Claude's rec)** | Visibility genuinely cannot be set from the publishing workflow on first push; same pattern as Phase 22's Dev Portal step | ✓ |
| Leave it private, document `docker login` | No manual step; contradicts CICD-03's whole point and walls off a recruiter who tries the pull | |

**User's choice:** Ship + manual public flip as HUMAN-UAT.

---

## Sequencing & extras

**Claude surfaced, unprompted:** the repo (`github.com/jadrianports/dexter`, already **PUBLIC**) is
**140 commits behind** local `main` — the entire v1.3 + v1.4 stack is unpushed, which means **`ci.yml` has
never actually executed.** Phases 19–22 were described as running "behind a green CI gate" that has only
ever existed as a file on disk, and `ci.yml`'s own Pitfall-7 comment predicts the native `davey`/PyNaCl
build may fail on the first real run. That made "when do we push" a design decision rather than bookkeeping.

### Q1 — When does the 140-commit push happen?

| Option | Description | Selected |
|--------|-------------|----------|
| First task of the phase — push, watch CI, fix what breaks **(Claude's rec)** | Find pre-existing CI breakage while it's an isolated fix, not tangled with a new Astro build, Pages deploy, and GHCR publish | ✓ |
| Push at the end with the phase's work included | One clean push; worst possible time to learn the gate never worked | |
| You decide | | |

**User's choice:** Push first.

### Q2 — Where does the landing page live?

| Option | Description | Selected |
|--------|-------------|----------|
| Default `jadrianports.github.io/dexter` **(Claude's rec)** | Zero cost, zero DNS; needs Astro's `base: '/dexter'` (a classic Pages footgun to lock down) | ✓ |
| Custom domain | Sharper; needs a domain, CNAME, DNS, propagation — none agent-verifiable | |

**User's choice:** Default github.io path.

### Q3 — Which badges?

| Option | Description | Selected |
|--------|-------------|----------|
| CI status + Python + discord.py + Postgres/pgvector + Gemini **(Claude's rec)** | Five reads as considered; twelve reads as padding | ✓ |
| CI status only | Maximum restraint; fails PORT-03's explicit "tech-stack badges" | |
| Full 8-badge set incl. license + GHCR | More complete; badge soup, and a license badge implies a LICENSE file that doesn't exist | |

**User's choice:** Five badges. License badge explicitly excluded.

**Note:** The "is the repo public / when does it go public" gray area Claude had queued was **dropped after
verification** — `gh repo view` confirmed the repo is already PUBLIC, so the question was moot.

---

## Claude's Discretion

The user made an affirmative choice on every question — no "you decide" selections. The following were
delegated to the planner in CONTEXT.md rather than asked:

- How the `dist/` drift scan is invoked (pytest-shelling-out vs standalone CI step), with the hard
  constraint that it must fail on drift and **never silently skip**, plus a required positive-control test.
- Whether `tests/test_invite_drift_guard.py` is extended or a sibling check is added (reuse the regex).
- Astro project layout, `package.json` scripts, Node version pinning.
- The mock's animation mechanism and `prefers-reduced-motion` handling.
- The Playwright GIF render pipeline (resolution, frame rate, duration, script location).
- Mermaid diagram content; which 3–4 hard-problem callouts make the cut.
- Exact landing-page copy, hero tagline, and disclosure wording.
- Workflow file names and job granularity; GHCR tag set beyond `:v*` + `:latest`.
- How the CI-repair contingency is structured (dedicated first plan vs a gating task).

## Deferred Ideas

- **A real screen-recorded demo** of the running bot (showing the Phase 7 now-playing embed + control
  buttons) — superseded by the HTML mock; a drop-in upgrade if a good take ever exists.
- **A `LICENSE` file + license badge** — excluded from the badge set; a separate trivial decision.
- **A custom domain** for the landing page — rejected; needs DNS no agent can verify.
- **A prod auto-deploy of the bot** — permanently out of scope this milestone (no prod host exists).
- **Runtime permission-gap self-diagnostic (`/permcheck`)** — carried over from Phase 22's deferred list.
- **A vanity/short invite link** — ruled out by Phase 22 D-07; defeats the literal-match drift guard.
