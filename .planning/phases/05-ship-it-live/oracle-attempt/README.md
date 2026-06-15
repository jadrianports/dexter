# Oracle attempt (superseded 2026-06-15)

Phase 5 was first planned + executed against **Oracle A1 + Docker Postgres + OCI**.
It was then re-targeted to **Koyeb (WEB service) + Neon serverless Postgres** (see ../05-CONTEXT.md, K-01…K-18).

These are the original Oracle planning + execution artifacts, archived intact:
- 05-01/02/03-PLAN.md + matching SUMMARY.md — Oracle plans + execution summaries
- 05-REVIEW.md / 05-VERIFICATION.md — Oracle code review + verification (human_needed)
- 05-ARTIFACTS.md — Oracle plan manifest
- 05-PATTERNS.md / 05-VALIDATION.md — Oracle planning aids (regenerated fresh for Koyeb+Neon)

The code fixes P-01…P-03 (reconnect-race guard, clear_persisted gaps, TZ-correct roast) are substrate-agnostic and remain committed on main — NOT superseded.
