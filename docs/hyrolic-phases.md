# Hyrolic — Execution Plan & Phase Timeline

Project: construction-site scanning platform (Go2 Air robot + Jetson edge +
cloud AI + BIM comparison). Written 2026-09-11.

Honest bottom line: 8-14 months to a client-ready product if built mostly
solo. The robot (hardware integration) is the biggest schedule risk, not the
AI. A software-first prototype (no robot) gets you a sellable pipeline in
4-6 weeks.

---

## SEQUENCING STRATEGY (read this first)

De-risk the cheap part before buying hardware:

  PHASE A (weeks 1-6): iPhone LiDAR / handheld scanner -> full cloud +
  platform + semantics stack. Produces: vector search, BIM matching demo,
  inspection reports, dashboard, sellable pipeline video.

  PHASES 0+ (after): the Go2 Air robot becomes a drop-in replacement for the
  capture step only. The moat (feedback loop + semantics) is software; the
  robot is a commodity input.

Rationale: Go2 Air ~$15k+ with sensors, Jetson Orin ~$2k. Don't burn money and
months on robot integration before the software is proven.

---

## PHASES & ESTIMATES (for the full robot product)

Phase 0 — Feasibility spike (2-4 weeks)
  - Get Go2 Air + Jetson talking: ROS, SDK, LiDAR + camera sync
  - ONE real site walk -> one aligned point cloud
  - Expose hardware hell early: SDK quirks, power/thermals, drift
  - KILL-OR-CONTINUE GATE: if one clean scan takes >2 weeks, revise plan

Phase 1 — Edge pipeline (4-8 weeks, realistic 6)
  - SLAM / registration (LiDAR-inertial: FAST-LIO / LIO-SAM candidates)
  - Filter + compress
  - Basic on-edge inference
  - Sync rule: derived data now, raw on demand

Phase 2 — Cloud AI (4-6 weeks)
  - Object storage (raw point clouds versioned + processed scenes)
  - Pretrained detection / segmentation, 3D reconstruction
  - Retraining plumbing

Phase 3 — BIM comparison + semantic matcher (3-6 weeks)
  - Geometric as-built vs BIM compare
  - EMBEDDING-based fuzzy matching (differentiator): detection labels vs BIM
    object names via embeddings + cosine sim, geometry as second-pass scorer
  - Fastest phase per complexity given ML background

Phase 4 — Vector DB + search / RAG / clustering (2-4 weeks)
  - pgvector or Qdrant, embed findings + observations
  - Semantic report search, cross-site failure clustering, RAG Q&A
  - Fastest phase overall (already studied this stack)

Phase 5 — Platform UI (3-6 weeks)
  - Deviations, progress, inspection reports, dashboard
  - Outsource frontend to compress

Phase 6 — QA loop + labeling + multi-site (4-8 weeks, ongoing)
  - Human sign-off gate before reports leave system
  - Corrections -> labeled set -> retrain -> redeploy to edge
  - Re-scan missions from flagged areas
  - Labeling throughput is a treadmill, not a milestone

TOTAL: ~9-12 months effort. Add 20-40% for site logistics (access, permissions,
weather, safety) -> 8-14 months realistic. Full-time ~1.5x faster, part-time
~2x slower.

---

## RISK REGISTER (top items)

  1. SLAM/hardware integration — biggest technical risk (hardware hell +
     drift). De-risk with early feasibility spike; consider cloud-side
     alignment fallback.
  2. Labeled construction data — detection/segmentation quality depends on it.
     Decide: internal, outsourced (Scale/Labelbox), or pretrained datasets.
  3. Trust/QA — a report flagging 300 issues when 3 are real kills the product.
     Human QA gate is non-negotiable.
  4. Cost creep — Go2 Air (~$15k+), Jetson (~$2k), cloud storage for point
     clouds. Phase A software prototype avoids most of this until proven.

---

## DEPENDENCIES BETWEEN PHASES

  Phase 0 -> Phase 1 (hardware must work first)
  Phase 1 -> Phase 2 (cloud needs edge output)
  Phases 2+3 -> Phase 4 (vector DB needs findings + BIM entities)
  Phase 2+4 -> Phase 5 (platform needs data behind it)
  Phase 5 -> Phase 6 (QA gate sits on platform output)
  Phase 6 -> back to Phases 1-4 (feedback loop)

Phases 2-5 can partially overlap: start platform UI mockup early, start
labeling collection the day Phase 0 succeeds.

---

## 6-WEEK SOFTWARE-FIRST PROTOTYPE (Phase A detailed)

  Week 1:  Capture 2-3 sites with iPhone LiDAR (or phone photogrammetry) ->
            aligned point clouds + photos
  Week 2:  Cloud storage + embedding pipeline (chunk observations, embed)
  Week 3:  Vector DB + semantic search (natural-language queries over scans)
  Week 4:  BIM semantic matcher: mock BIM objects vs scan detections,
            embeddings + geometry hybrid scorer
  Week 5:  Reports + deviations UI + dashboard
  Week 6:  QA gate + demo video + pricing call deck

Deliverable: a working pipeline you can demo to a GC/developer, and a
foundation the robot drops into.

---

## NEXT ACTIONS

  1. Decide: software-first prototype (recommended) or straight to robot
  2. If prototype: pick first demo site + start Week 1 captures
  3. In parallel: research SLAM stack choice (Phase 0 prep)
  4. Push this plan to a repo (hyrolic) for versioning

Source doc: hyrolic/docs/workflow.md (gap list + ideal workflow diagram)