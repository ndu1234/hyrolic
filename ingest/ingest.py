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

POINT_CLOUD_EXTS = {".ply", ".obj", ".glb", ".gltf", ".las", ".laz", ".e57"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".dng", ".tiff", ".tif"}
MESH_EXTS = {".obj", ".glb", ".gltf"}

MANIFEST_VERSION = 1


def read_ply_header(path: Path) -> dict:
    """Parse a PLY header (ASCII header, binary or ASCII body)."""
    with open(path, "rb") as fh:
        head = fh.read(4096)
    end = head.find(b"end_header\n")
    if end == -1:
        # header longer than 4KB — scan until end_header
        with open(path, "rb") as fh:
            head = b""
            while b"end_header\n" not in head:
                chunk = fh.read(4096)
                if not chunk:
                    break
                head += chunk
                if len(head) > 1_000_000:
                    break
        end = head.find(b"end_header\n")
        if end == -1:
            return {"error": "no end_header found"}
    header = head[:end].decode("ascii", errors="replace")
    fmt = "binary" if "binary_little_endian" in header or "binary_big_endian" in header else "ascii"
    props: dict = {"format": fmt}
    n_vertices = 0
    n_faces = 0
    has_color = False
    in_element = None
    for line in header.splitlines():
        line = line.strip()
        if line.startswith("element "):
            parts = line.split()
            in_element = parts[1]
            n = int(parts[2])
            if in_element == "vertex":
                n_vertices = n
            elif in_element == "face":
                n_faces = n
        elif line.startswith("property "):
            parts = line.split()
            pname = parts[-1]
            if in_element == "vertex" and pname in ("red", "green", "blue", "r", "g", "b", "alpha"):
                has_color = True
    props["vertices"] = n_vertices
    props["faces"] = n_faces
    props["has_vertex_color"] = has_color
    return props


def describe_file(path: Path) -> dict:
    ext = path.suffix.lower()
    stat = path.stat()
    entry = {
        "name": path.name,
        "path": str(path.relative_to(path.parents[2])),
        "format": ext.lstrip("."),
        "bytes": stat.st_size,
        "modified": date.fromtimestamp(stat.st_mtime).isoformat(),
    }
    if ext == ".ply":
        entry["ply"] = read_ply_header(path)
    return entry


def scan_site(site_dir: Path) -> dict:
    meta_path = site_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())

    clouds, photos, other = [], [], []
    for p in sorted(site_dir.rglob("*")):
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
            clouds.append(describe_file(p))  # mesh doubles as cloud-ish
        else:
            other.append(str(p.relative_to(site_dir)))

    scan_dirs = sorted({p.parent for p in site_dir.rglob("raw")}) if any(p.name == "raw" for p in site_dir.rglob("raw")) else []

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated": date.today().isoformat(),
        "site": site_dir.name,
        "meta": meta,
        "scans": [str(d.relative_to(site_dir)) for d in scan_dirs] or ["raw"],
        "point_clouds": clouds,
        "photos": {"count": len(photos), "files": photos},
        "other_files": other,
    }

    # validation
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", type=str, help="path to a site folder")
    ap.add_argument("--all", action="store_true", help="ingest every site under data/sites/")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    sites_root = root / "data" / "sites"

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

    rc = 0
    for sd in site_dirs:
        if not sd.is_dir():
            print(f"SKIP {sd}: not a directory", file=sys.stderr)
            continue
        manifest = scan_site(sd)
        out = sd / "manifest.json"
        out.write_text(json.dumps(manifest, indent=2))
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