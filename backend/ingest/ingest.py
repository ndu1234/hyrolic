#!/usr/bin/env python3
"""Hyrolic ingest (Phase 1): normalize site captures into a manifest.

Reads raw PLY/OBJ/GLB point clouds + photos from a site folder and writes
manifest.json WITHOUT loading full point clouds into memory.

Usage:
    python3 ingest/ingest.py --site data/sites/<site-name>
    python3 ingest/ingest.py --all          # every site under data/sites/
"""

import argparse
import json
import os
import struct
import sys
from datetime import date
from pathlib import Path

# ── File type sets ─────────────────────────────────────────────
# These define which file extensions we recognize as point clouds,
# photos, or mesh files (meshes double as cloud-like geometry).
POINT_CLOUD_EXTS = {".ply", ".obj", ".glb", ".gltf", ".las", ".laz", ".e57"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".dng", ".tiff", ".tif"}
MESH_EXTS = {".obj", ".glb", ".gltf"}

MANIFEST_VERSION = 1


def read_ply_header(path: Path) -> dict:
    """Parse the ASCII header of a PLY file (supports binary or ASCII body).

    Returns a dict with: format, vertex count, face count, has_vertex_color flag.
    Only reads the header text — never loads the full point cloud into memory.
    This is key for large scans that could be hundreds of MB.

    The PLY format: ASCII header lines ending with 'end_header', then binary or
    ASCII vertex data. We search for 'end_header' and parse the element/property
    lines above it.
    """
    # Read first 4KB — typical PLY headers are small
    with open(path, "rb") as fh:
        head = fh.read(4096)

    # Locate the end-of-header marker
    end = head.find(b"end_header\n")
    if end == -1:
        # Header is larger than 4KB — rare but possible for files with
        # many property definitions. Scan forward until we find it.
        with open(path, "rb") as fh:
            head = b""
            while b"end_header\n" not in head:
                chunk = fh.read(4096)
                if not chunk:
                    break
                head += chunk
                if len(head) > 1_000_000:
                    # Safety valve: headers should never be this large
                    break
        end = head.find(b"end_header\n")
        if end == -1:
            return {"error": "no end_header found"}

    # Decode the header text and determine format
    header = head[:end].decode("ascii", errors="replace")
    fmt = "binary" if "binary_little_endian" in header or "binary_big_endian" in header else "ascii"
    props: dict = {"format": fmt}

    # Walk through header lines to extract vertex count, face count, and color info
    n_vertices = 0
    n_faces = 0
    has_color = False
    in_element = None

    for line in header.splitlines():
        line = line.strip()
        if line.startswith("element "):
            # 'element vertex 76308' or 'element face 0'
            parts = line.split()
            in_element = parts[1]
            n = int(parts[2])
            if in_element == "vertex":
                n_vertices = n
            elif in_element == "face":
                n_faces = n
        elif line.startswith("property "):
            # 'property float x' or 'property uchar red'
            parts = line.split()
            pname = parts[-1]
            if in_element == "vertex" and pname in ("red", "green", "blue", "r", "g", "b", "alpha"):
                has_color = True

    props["vertices"] = n_vertices
    props["faces"] = n_faces
    props["has_vertex_color"] = has_color
    return props


def describe_file(path: Path) -> dict:
    """Create a metadata entry for a single file in the scan folder.

    Records name, relative path, format, byte size, modification date.
    For PLY files, also includes the parsed header (vertex count, colors, etc.).
    """
    ext = path.suffix.lower()
    stat = path.stat()
    entry = {
        "name": path.name,
        # Relative path from the site folder (parents[2] = site dir, e.g. data/sites/test-site-01)
        "path": str(path.relative_to(path.parents[2])),
        "format": ext.lstrip("."),
        "bytes": stat.st_size,
        "modified": date.fromtimestamp(stat.st_mtime).isoformat(),
    }
    # For PLY files, enrich with header info (vertices, colors, etc.)
    if ext == ".ply":
        entry["ply"] = read_ply_header(path)
    return entry


def scan_site(site_dir: Path) -> dict:
    """Walk a site directory and produce a manifest dict.

    Expected structure:
      data/sites/<site-name>/
        meta.json           (site metadata: name, date, scanner, notes)
        <scan-date>/
          raw/
            scan-01.ply     (point cloud files)
            photos/         (reference photos, optional)

    Returns a manifest dict with validation errors if anything is wrong.
    """
    # Load site metadata if it exists
    meta_path = site_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())

    # Categorize every file under the site directory
    clouds, photos, other = [], [], []
    for p in sorted(site_dir.rglob("*")):
        # Skip directories, git internals, and meta.json itself
        if not p.is_file() or ".git" in p.parts:
            continue
        if p.name == "meta.json":
            continue

        ext = p.suffix.lower()
        if ext in POINT_CLOUD_EXTS:
            clouds.append(describe_file(p))
        elif ext in PHOTO_EXTS:
            photos.append(describe_file(p))
        elif ext in MESH_EXTS:
            # Mesh files (OBJ, GLB) can be treated as point-cloud-adjacent geometry
            clouds.append(describe_file(p))
        else:
            other.append(str(p.relative_to(site_dir)))

    # Find scan directories (containing 'raw' subdirectories)
    scan_dirs = sorted({p.parent for p in site_dir.rglob("raw")}) if any(p.name == "raw" for p in site_dir.rglob("raw")) else []

    # Build the manifest
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated": date.today().isoformat(),
        "site": site_dir.name,
        "meta": meta,
        # List of scan subdirectories, falling back to ["raw"] if no nested structure
        "scans": [str(d.relative_to(site_dir)) for d in scan_dirs] or ["raw"],
        "point_clouds": clouds,
        "photos": {"count": len(photos), "files": photos},
        "other_files": other,
    }

    # ── Validation ─────────────────────────────────────────
    errors = []
    if not clouds:
        errors.append("no point-cloud files found (.ply/.obj/.glb/.las/.laz/.e57)")
    broken = [c["name"] for c in clouds if c.get("ply", {}).get("error")]
    if broken:
        errors.append(f"unreadable PLY headers: {broken}")
    if not meta:
        errors.append("meta.json missing — add site name, date, scanner, device, notes")
    manifest["errors"] = errors
    return manifest


def main() -> int:
    """Entry point: parse args, iterate sites, generate manifests."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", type=str, help="path to a site folder")
    ap.add_argument("--all", action="store_true", help="ingest every site under data/sites/")
    args = ap.parse_args()

    # Resolve paths relative to the repo root (grandparent of backend/ingest/)
    root = Path(__file__).resolve().parents[2]
    sites_root = root / "data" / "sites"

    # Determine which sites to process
    if args.site:
        site_dirs = [Path(args.site)]
    elif args.all:
        site_dirs = sorted(sites_root.iterdir()) if sites_root.exists() else []
    else:
        print("provide --site <path> or --all", file=sys.stderr)
        return 2

    if not site_dirs:
        print("no sites found under data/sites/", file=sys.stderr)
        return 1

    # Process each site directory
    rc = 0
    for sd in site_dirs:
        if not sd.is_dir():
            print(f"SKIP {sd}: not a directory", file=sys.stderr)
            continue

        manifest = scan_site(sd)
        out = sd / "manifest.json"
        out.write_text(json.dumps(manifest, indent=2))

        # Report results
        status = "OK " if not manifest["errors"] else "ERR"
        print(f"{status} {sd.name}: {len(manifest['point_clouds'])} cloud(s), "
              f"{manifest['photos']['count']} photo(s)")
        for e in manifest["errors"]:
            print(f"     ! {e}", file=sys.stderr)
        if manifest["errors"]:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
