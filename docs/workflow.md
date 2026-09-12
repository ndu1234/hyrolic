# Hyrolic — Construction Intelligence Architecture (v0.4)

Status: corrected for Go2 X hardware + sensor reality.

---

## 1. The hardware reality

**Unitree Go2 X** — the robot we're building for:

| Sensor | What it gives us | Accuracy | Purpose |
|---|---|---|---|
| 4D LiDAR L1 | Point clouds (~20k pts/s) | ±2 cm sensor, ±5-10 cm after SLAM | Rough 3D context, robot localization |
| HD wide-angle camera | RGB images (1280x720, 120° FOV) | Pixel resolution | Object detection, visual condition |
| Wireless Vector Positioning | Robot pose / odometry | ~cm-level drift over distance | Where the robot is in the site |
| Optional D435i | Aligned RGB + depth | ~cm at close range | Close-up inspection |

**Critical constraint:** L1 is an obstacle-avoidance LiDAR, not a survey scanner. Compare to a Faro/Leica tripod (millions of pts/s, mm accuracy). The L1 gives us ~20k pts/s at ±2 cm, which after SLAM drift and BIM registration lands at **±5-10 cm positional uncertainty**.

This is fine for what the system can honestly do — and defines what it cannot.

---

## 2. What the system can and cannot do

| CAN do (reliably) | CANNOT do |
|---|---|
| Detect if an element exists (wall built? column poured?) | Measure rebar spacing to the mm |
| Check rough position (pipe in the right zone?) | Verify structural tolerances |
| Track progress over time (was here last week, not there now) | Replace a total station survey |
| Find missing or extra elements vs BIM | MEP fit-out precision checks |
| Flag coarse clashes (>10 cm offset) | Final sign-off inspection |
| Visual condition assessment (camera-based) | Detect hairline cracks |
| Cross-site trend analysis (rebar failures cluster in winter) | One-shot precision measurement |

**The honest sell:** automated daily walkthroughs that flag issues for human follow-up with proper tools. Not replacing surveyors — augmenting them.

---

## 3. The pipeline (dual-sensor)

```
GO2 X WALKS THE SITE (autonomous or teleop)
│
├── 4D LiDAR L1 → sparse point clouds
├── HD camera → RGB frames (every ~1-2 sec)
└── Odometry → robot pose per frame
     │
     ▼
EDGE (Jetson Orin or onboard 8-core)
│
├── LIDAR PIPELINE:
│   ├── SLAM / registration (LiDAR-inertial, e.g. FAST-LIO)
│   │   → aligned point cloud of the site walk
│   │   → robot trajectory + per-frame poses
│   └── Coarse geometry extraction
│       → floor / wall planes (RANSAC)
│       → object clusters (Euclidean)
│       → rough bounding boxes
│
├── CAMERA PIPELINE:
│   ├── Object detection on RGB frames (YOLOv8)
│   │   → "column", "rebar", "pipe", "wall", "door"
│   │   → 2D bounding boxes + confidence
│   ├── Multi-object tracking across frames
│   │   → "this is Column A1, seen 47 times"
│   └── Project to 3D using LiDAR pose
│       → rough 3D position (±10 cm)
│
└── MERGE → detected-site-model.json
    └── objects with: type, 3D position (approx), dimensions (approx),
        confidence, camera frames as evidence
     │
     ▼
CLOUD
│
├── BIM INGESTION
│   ├── IFC → structured object list
│   │   (columns, walls, slabs, rebar, pipe, doors…)
│   ├── Each object: type, position, dimensions, material
│   └── For Phase A: mock BIM JSON (we have this)
│
├── BIM COMPARISON (tolerance-aware)
│   ├── 1. Presence check: is each BIM object detected?
│   │   → "Wall B: MISSING (not found within 50 cm of BIM position)"
│   ├── 2. Position check: is it in the right zone?
│   │   → "Column A1: offset 8 cm east (WITHIN TOLERANCE ±10 cm)"
│   │   → "Pipe run 1: offset 22 cm south (FLAGGED)"
│   ├── 3. Extra elements: anything detected that BIM doesn't have?
│   │   → "Unidentified rebar cluster at (-3, 0, 5)"
│   ├── 4. Progress check (multi-scan): what changed?
│   │   → "Column B2: not present in scan 1, present in scan 2"
│   └── 5. Visual condition (from camera frames)
│       → "Rebar cluster A: rust visible (see frame 47.jpg)"
│
├── SEMANTIC MATCHER (the differentiator)
│   ├── Embedding-based fuzzy name matching
│   │   → "HVAC duct 3" vs "duct, level 2, zone A" → match via cosine sim
│   ├── Geometric scorer as second pass
│   │   → Position + size comparison within tolerance
│   └── Handles construction-site naming chaos
│
├── VECTOR DB (pgvector / Qdrant)
│   ├── Embed deviation reports + observations
│   ├── Semantic search: "show me everywhere rebar spacing looks off"
│   ├── Cross-site clustering: recurring failure patterns
│   └── RAG: "what changed since Thursday's scan?"
│
└── PLATFORM
    ├── Dashboard: site overview, progress %, deviation count
    ├── Inspection reports: per-scan, per-element
    ├── Time-lapse: overlay scans over time
    └── QA gate: human sign-off before reports leave system
         │
         ▼
FEEDBACK LOOPS (the moat)
├── QA corrections → labeled data → retrain YOLO
│   → Model gets better at detecting construction elements
├── QA corrections → fine-tune semantic matcher
├── Missed / flagged areas → re-scan mission for robot
└── Cross-site patterns → product insight reports
```

---

## 4. What this means for the data model

The site model uses **tolerance zones** not exact coordinates:

```json
{
  "detected_object": {
    "type": "column",
    "bim_match": "col-01 (Column A1)",
    "position_3d": {"x": 3.08, "y": 0.02, "z": -1.94},
    "position_uncertainty": 0.08,
    "bim_position": {"x": 3.0, "y": 0.0, "z": -2.0},
    "offset": 0.12,
    "tolerance": 0.10,
    "flagged": true,
    "evidence": {"frame": "frame_0047.jpg", "confidence": 0.91}
  }
}
```

---

## 5. Embeddings fit (unchanged from v0.3)

| Use case | Embed what | Compare with | Output |
|---|---|---|---|
| Report search | deviation text | cosine sim | ranked matches |
| BIM matching | detection labels vs BIM object names | embeddings + geometry hybrid | matched elements |
| Site clustering | deviation reports | k-means/DBSCAN on vectors | failure-pattern groups |
| Q&A (RAG) | report chunks | retrieval | grounded answers |

---

## 6. Open questions (updated for Go2 X)

- SLAM: FAST-LIO / LIO-SAM on edge, or use Go2 X's built-in odometry?
- Edge compute: Jetson Orin strapped to robot, or send raw data over 5G?
- Camera + LiDAR fusion: at what level? (pixel-level, object-level, or both separately?)
- D435i: worth adding for close-up depth, or HD camera + LiDAR projection sufficient?
- Labeling: YOLO needs construction-site training data — use pretrained weights + fine-tune on site captures?
- Tolerance: what's the default per element type? (±10 cm structural, ±15 cm MEP?)

---

## 7. Next steps

- [ ] Build synthetic image generator (render the test PLY from camera POVs)
- [ ] Stand up YOLO detection pipeline on synthetic images
- [ ] Build BIM comparison engine with tolerance zones
- [ ] Integrate LiDAR + camera pipelines
- [ ] Update Phase A plan to reflect dual-sensor approach
