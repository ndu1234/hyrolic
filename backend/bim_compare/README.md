# bim_compare/ — BIM Comparison Engine

Compares detected site objects against the BIM model with tolerance-aware matching.

## Files

- `compare.py` — Tolerance-aware BIM vs detected comparison. Presence check, position check (within ±10cm zones), extra elements, progress over time.
- `semantic_matcher.py` — Embedding-based fuzzy name matching. Handles "HVAC duct 3" vs "duct, level 2, zone A" mismatches using cosine similarity + geometric scorer.
- `report.py` — Generates deviation reports in structured JSON and human-readable formats.

## Input

- BIM model from `data/bim/` (mock JSON for now, IFC parser later)
- Detected site model from `detection/`

## Output

- Deviation report: missing elements, positional offsets, extra elements, progress deltas, visual evidence.
