# Hyrolic — Construction Intelligence Workflow (v0.3)

First-pass spec for Hyrolic: a construction-site scanning platform built on a
Unitree Go2 Air robot dog (LiDAR + cameras), NVIDIA Jetson edge compute, and a
cloud AI + BIM comparison layer.

Status: draft for discussion. Original diagram (linear, one-scan view) reviewed
2026-09-11; this doc is the revised loop version.

---

## 1. The pipeline (as originally drawn)

  Construction site
    -> Go2 Air robot (LiDAR, cameras, IMU/nav, mobility) -> raw site data
    -> Edge computer (NVIDIA Jetson, Docker, ROS/robot SDK, filtering,
       compression, basic inference)
    -> Server/cloud (Wi-Fi / 5G / Ethernet): object detection, segmentation,
       3D processing, BIM comparison, AI models
    -> Construction intelligence platform: as-built vs BIM, deviations,
       progress, inspection reports, dashboard

## 2. What changes (the gap list)

Linear diagram = describes ONE scan, not a product. Fixes:

1. **Embedding-based semantic search on reports** — embed deviations and
   observations so staff can query "anywhere the rebar spacing looks off" and
   get ranked matches. Keyword grep fails on site language.
2. **BIM matching via embeddings + geometry** — match point-cloud detections to
   BIM objects with embeddings/cosine sim for fuzzy name+type matching, then
   geometric checks (position/size) as a second-pass scorer. Handles
   "HVAC duct 3" vs "duct, level 2, zone A" mismatches.
3. **Cross-site clustering** — embed deviation reports across projects; clusters
   surface recurring failure patterns ("rebar spacing misses cluster in winter
   pours"). Sells as an insight product, not just a report.
4. **RAG over scan history** — "what changed since Thursday's scan?" answered
   via embed + retrieve + LLM. Textbook tokenize -> embed -> cosine sim flow.
5. **SLAM/registration step** — LiDAR + IMU drift over a full site walk; raw
   point clouds must be aligned before 3D processing. This is the hardest
   missing block; "raw site data -> 3D processing" hides it.
6. **Edge vs cloud data-flow rule** — full-res LiDAR + video is GBs per scan.
   Decide at the edge: send derived/compressed data now, keep raw local, ship
   raw on demand. No blanket "compress then send everything."
7. **Labeling loop** — detection/segmentation models need labeled construction
   data. Define internal or outsourced labeling + a retraining cadence, or the
   "AI models" box is a placeholder.
8. **Feedback loop (the big one)** — nothing in the original diagram ever
   improves the system. Deviations should feed back to (a) the models
   (fine-tuning data) and (b) the robot (re-scan flagged areas at higher
   resolution). Without this the platform is static.
9. **BIM ingestion spec** — "BIM comparison" needs a source model. Define IFC
   ingestion: from whom, which disciplines (architectural/MEP/structural), how
   often updated.
10. **QA/validation gate** — a report flagging 300 issues when 3 are real kills
    trust. Human-in-the-loop sign-off before inspection reports leave the
    system. Selling inspection-grade data.
11. **Storage + vector layer** — embeddings (items 1-4) need a home: pgvector
    or Qdrant. Add "vector DB" between cloud AI and the platform.

## 3. Ideal workflow (the loop)

  SITE
  -> Go2 Air walk (LiDAR + cameras + IMU)
  -> SLAM / registration -> aligned scene
  -> EDGE (Jetson): filter, compress, basic detection;
     decide: derived data now, raw on demand
  -> CLOUD STORAGE: raw point clouds (versioned) + processed scenes
  -> CLOUD AI: detection/segmentation (retrained) -> 3D reconstruction
     -> geometric BIM comparison + embedding-based semantic matching
  -> VECTOR DB: findings + observations embedded
     (semantic search, clustering, RAG)
  -> PLATFORM: deviations, progress, inspection reports, dashboard
  -> QA REVIEW: human sign-off of flagged issues
  -> FEEDBACK: corrections -> labeling set -> retrain
              missed areas -> robot re-scan mission
  -> back to SITE

The moat: the loop. Your original ends at the dashboard; the ideal version
returns to the robot and the models. Competitors do point-cloud alignment;
almost nobody closes the semantic + retraining loop.

Diagram: hyrolic-workflow.html (same directory).

## 4. Embeddings fit (ties to the study session)

| Use case | Embed what | Compare with | Output |
|---|---|---|---|
| Report search | deviation text | cosine sim | ranked matches |
| BIM matching | detection labels vs BIM object names | embeddings + geometry hybrid | matched elements |
| Site clustering | deviation reports | k-means/DBSCAN on vectors | failure-pattern groups |
| Q&A (RAG) | report chunks | retrieval | grounded answers |

## 5. Open questions

- SLAM stack: LiDAR-inertial (e.g. FAST-LIO / LIO-SAM) on the Jetson, or
  cloud-side alignment?
- Cloud: which vendor, and where do raw point clouds live (object storage)?
- Vector store: pgvector (Postgres, easiest) vs Qdrant (purpose-built)?
- Labeling: internal team, outsourced (Scale/Labelbox), or start with
  pretrained construction datasets?
- Multi-robot / multi-site: single Go2 Air per site for v1, but the data model
  should assume many sites.

## 6. Next steps

- [ ] Decide SLAM approach (biggest technical risk)
- [ ] Pick vector store (pgvector is fine to start)
- [ ] Stand up labeling pipeline for first construction dataset
- [ ] Build BIM semantic matcher demo (embedding + geometry hybrid)
- [ ] Sketch data schema: sites, scans, deviations, reports, embeddings