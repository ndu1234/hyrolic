# platform/ — Web UI

Construction intelligence dashboard, inspection reports, and QA gate.

## Files

- `dashboard.html` — Site overview, progress %, deviation counts per scan.
- `reports.html` — Per-scan, per-element inspection reports with time-lapse overlay.
- `qa_gate.html` — Human sign-off interface before reports leave the system.

## Stack

Plain HTML/CSS/JS + Supabase (same pattern as LocalEyes). No build step.
