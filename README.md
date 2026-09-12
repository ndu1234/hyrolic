# Hyrolic — Construction Intelligence Platform

Automated construction-site scanning and BIM comparison using a **Unitree Go2 X** robot with 4D LiDAR + HD cameras. Detect deviations between as-built conditions and BIM models, track progress over time, and surface failure patterns across sites.

---

## Hardware

| Component | Spec | Purpose |
|---|---|---|
| Unitree Go2 X | Quadruped robot, 8-core onboard compute | Site walkthrough, data collection |
| 4D LiDAR L1 | 360°x90°, ~20k pts/s, ±2cm accuracy | Rough 3D geometry, robot localization |
| HD wide-angle camera | 1280x720, 120° FOV | Object detection, visual inspection |
| Optional D435i | Aligned RGB + depth | Close-up depth inspection |

**Critical constraint:** The L1 is an obstacle-avoidance LiDAR, not a survey scanner. After SLAM drift + BIM registration, positional uncertainty is **±5-10cm**. The system is designed for progress tracking and coarse QA, not millimeter-precision survey work.

---

## Pipeline Overview

```
GO2 X walks site → LiDAR point clouds + camera frames → Edge processing
→ Cloud AI (detection, BIM comparison, semantic matching) → Platform UI
→ QA review → Feedback loops (retrain models, re-scan missions)
```

---

## Project Structure

```
hyrolic/
│
├── backend/           # All backend processing code
│   ├── ingest/        # Data ingestion (normalize captures into manifests)
│   │   ├── ingest.py             # PLY point-cloud manifest generator
│   │   ├── ingest_frames.py      # Camera frame indexer (placeholder)
│   │   └── generate_test_data.py # Synthetic PLY + BIM generator
│   │
│   ├── detection/     # Computer vision pipeline (YOLO + tracking)
│   │   ├── detect.py             # YOLOv8 inference on camera frames
│   │   ├── tracker.py            # Multi-object tracking across frames
│   │   └── project_3d.py         # Project 2D detections → 3D coordinates
│   │
│   ├── bim_compare/   # BIM comparison engine (tolerance-aware)
│   │   ├── compare.py            # Presence/position/extra/progress checks
│   │   ├── semantic_matcher.py   # Embedding-based fuzzy name matching
│   │   └── report.py             # Deviation report generator
│   │
│   ├── vector_db/     # Embedding + search layer
│   │   ├── embed.py              # Chunk + embed observations
│   │   ├── search.py             # Semantic search + RAG
│   │   └── cluster.py            # Cross-site failure-pattern clustering
│   │
│   └── scripts/       # Orchestration and automation
│       ├── run_pipeline.py       # End-to-end: frames → BIM compare
│       └── synthetic_run.py      # Run full pipeline on synthetic test data
│
├── frontend/          # Web UI (plain HTML/CSS/JS + Supabase)
│   ├── dashboard.html       # Site overview, progress, deviations
│   ├── compare.html         # Split-view: Go2 X capture vs BIM model
│   ├── reports.html         # Per-scan inspection reports
│   └── qa_gate.html         # Human sign-off interface
│
├── data/              # All site data and test fixtures
│   ├── bim/           # BIM model JSON files (mock or real IFC exports)
│   ├── sites/         # Real captures from the robot (or iPhone)
│   │   └── <site-name>/
│   │       ├── meta.json
│   │       ├── manifest.json       # LiDAR file index (from ingest.py)
│   │       └── <scan-date>/
│   │           ├── raw/            # PLY point clouds from LiDAR
│   │           └── frames/         # RGB frames from camera
│   └── synthetic/     # Rendered test images from synthetic PLY scenes
│
├── capture/           # Capture protocols and shooting checklists
│   └── CAPTURE_KIT.md
│
├── docs/              # Architecture docs, diagrams, execution plans
│   ├── workflow.md           # Main spec (v0.4) — read this first
│   ├── hyrolic-workflow.html # SVG pipeline diagram
│   └── hyrolic-phases.md     # Timeline and execution plan
│
└── README.md          # This file
```

---

## What Each Module Does

### backend/ingest/
Normalizes raw captures into structured manifests. `ingest.py` reads PLY headers without loading the full point cloud, then writes a `manifest.json` for each site. `generate_test_data.py` creates synthetic construction scenes for testing the pipeline without a robot.

### backend/detection/
Runs YOLOv8 on camera frames to identify construction elements (columns, walls, rebar, pipes, doors). Tracks objects across frames to deduplicate detections. Projects 2D bounding boxes into 3D site coordinates using the robot's odometry and LiDAR alignment.

### backend/bim_compare/
The core comparison engine. Takes detected objects and BIM objects, then runs:
- **Presence check** — is every BIM object detected on site?
- **Position check** — is it in the right zone (±10cm tolerance)?
- **Extra elements** — anything on site that BIM doesn't have?
- **Progress check** — what changed between scans?

Uses embedding-based semantic matching to handle construction-site naming chaos ("HVAC duct 3" vs "duct, level 2, zone A").

### backend/vector_db/
Embeds deviation reports and observations for semantic search, cross-site clustering, and RAG query answering. Backend: pgvector for v1 (easiest setup), Qdrant if needed later.

### frontend/
Web dashboard showing site overview, progress tracking, inspection reports, a **split-view comparison** (Go2 X capture vs BIM model side-by-side), and a QA sign-off gate. Plain HTML/CSS/JS + Supabase — no build step, same pattern as LocalEyes.

---

## Status

| Module | Status | What's missing |
|---|---|---|
| docs/workflow.md | v0.4 (updated) | Nothing — current |
| docs/hyrolic-phases.md | v0.3 (needs update) | Go2 X specs, dual-sensor timeline |
| docs/hyrolic-workflow.html | v0.3 (needs update) | SVG needs Go2 X + dual pipeline |
| capture/CAPTURE_KIT.md | v0.1 (needs rewrite) | iPhone LiDAR → Go2 X capture protocol |
| backend/ingest/ingest.py | Done | — |
| backend/ingest/ingest_frames.py | Placeholder | Needs implementation |
| backend/ingest/generate_test_data.py | Done | — |
| backend/detection/ | Empty | detect.py, tracker.py, project_3d.py |
| backend/bim_compare/ | Empty | compare.py, semantic_matcher.py, report.py |
| backend/vector_db/ | Empty | embed.py, search.py, cluster.py |
| frontend/compare.html | In progress | Split-view: PLY vs BIM rendering |
| frontend/ | Mostly empty | dashboard.html, reports.html, qa_gate.html |
| backend/scripts/ | Not created | run_pipeline.py, synthetic_run.py |

---

## Getting Started (without the robot)

```bash
# 1. Generate synthetic test data (point cloud + BIM)
python3 backend/ingest/generate_test_data.py

# 2. Ingest the test site
python3 backend/ingest/ingest.py --site data/sites/test-site-01

# 3. (Coming soon) Run detection on synthetic camera renders
python3 backend/detection/detect.py --site test-site-01

# 4. (Coming soon) Compare detections to BIM
python3 backend/bim_compare/compare.py --site test-site-01

# 5. View the split comparison
open frontend/compare.html
```

---

## The Moat (why this is different)

Competitors do point-cloud alignment. Almost nobody closes the **semantic + retraining loop**:

- QA corrections feed back into model training
- Flagged areas become re-scan missions for the robot
- Cross-site deviation clusters surface failure patterns ("rebar misses cluster in winter pours")
- Every scan improves the system

---

## Key Decisions (still open)

| Decision | Options | Status |
|---|---|---|
| SLAM stack | FAST-LIO, LIO-SAM, or Go2 X built-in odometry | Open |
| Edge compute | Jetson Orin strapped to robot, or 5G streaming | Open |
| Vector store | pgvector (v1) vs Qdrant (scale) | pgvector for now |
| Labeling pipeline | Internal, Scale/Labelbox, or pretrained datasets | Open |
| Default tolerances | ±10cm structural, ±15cm MEP | TBD |
| D435i depth camera | Worth adding for close-up inspection? | Open |

---

## Philosophy

Build the software first. The robot is a commodity input — the moat is in the feedback loops, semantic matching, and cross-site intelligence. Phase A proves the pipeline with iPhone LiDAR + synthetic data. The Go2 X drops in as a capture upgrade.
