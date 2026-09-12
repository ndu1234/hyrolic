# Phase 1 — Capture Kit (Week 1)

Goal: 2-3 aligned point clouds + photos of real construction sites, exported
in a format the ingest pipeline can digest.

---

## 1. Devices

- iPhone with LiDAR: 12 Pro / 13 Pro / 14 Pro / 15 Pro / 16 Pro (any).
  No LiDAR? Use Polycam photo mode (photogrammetry) instead — needs 150-300
  well-overlapped photos per area and more shooting discipline.
- A printed A4 target sheet (QR/aligned cross marker) to place in frame for
  cross-scan alignment reference. Optional but cheap insurance.

## 2. Capture App (pick one)

Recommendation order:

1. **Polycam** — LiDAR mode, "Large Scene" capture, best export control
   (PLY with color, UTM/Local coordinates, texture). Paid plans annoying but
   one-off export fine. Best quality for a demo.
2. **Scaniverse** (free, iOS) — world-scale LiDAR capture, exports PLY/OBJ,
   good enough for Phase 1.
3. **3D Scanner App** — fine, PLY export, occasionally noisier registration.

Export format (all apps):
- **Point cloud: PLY** (binary little-endian preferred), WITH vertex colors.
- **Mesh: OBJ or GLB** if the app produces one (backup to point cloud).
- Register/coordinate: local coordinates are fine for Phase 1; use the app's
  "region/location" or manual geo-tag if available. Do NOT need UTM yet.

## 3. Shooting checklist (each scan)

- [ ] Site access confirmed + safe walk route (hard hat / vest / boots)
- [ ] Walk in closed loops, not out-and-back (aids loop closure / alignment)
- [ ] 60-70% overlap between passes; scan walls at ~3-6 ft distance
- [ ] Capture fixed, distinctive targets (columns, door frames, survey marks)
      from at least 3 angles for later cross-scan alignment
- [ ] Avoid direct sun glare; early morning / overcast preferred
- [ ] Record: site name, date, time, device, scanner name, notes
      (what's under construction, what phases are visible)
- [ ] After capture: also take 10-20 phone photos of the same areas
      (reference + future texture/AI input)

## 4. Where files go

    data/sites/<site-name>/<scan-date-YYYYMMDD>/
      raw/
        scan-01.ply          (or .obj/.glb)
        photos/              (reference phone photos)
      meta.json              (site, date, scanner, device, notes)

Site name: lowercase-hyphen, e.g. `downtown-retail-fitout`.
Scan date: the day of capture, not the day you export.

## 5. What ingest.py does with it

    python3 ingest/ingest.py --site data/sites/<site-name>

- Scans the folder tree, finds point-cloud files + photos
- Reads PLY headers (point count, bounds, color info) WITHOUT loading the
  full cloud
- Writes data/sites/<site-name>/manifest.json — one line per file:
  type, format, bytes, point count, bounds, photo count
- Fails loudly if a file is unreadable or a scan has no point cloud

Manifest is the contract for Week 2 (embedding pipeline): it should never
re-parse raw PLYs again.

## 6. Acceptance (definition of done for Week 1)

- [ ] 2-3 sites captured, each with >= 1 aligned point cloud + photos
- [ ] Each site folder matches the spec above
- [ ] ingest.py runs clean on every site, manifest.json exists
- [ ] Low-quality capture retaken (rule of thumb: can you visually identify
      walls, columns, openings in the cloud? if not, reshoot)

## 7. Pitfalls

- LiDAR range is ~5m: don't try to capture tall rooms in one pass — walk it.
- Mirrors, glass, dark surfaces = holes in the cloud. Note them in meta.json,
  don't chase them.
- Empty sites are BETTER for Phase 1 (cleaner clouds, easier BIM comparison
  later than cluttered ones), as long as there's visible structure.