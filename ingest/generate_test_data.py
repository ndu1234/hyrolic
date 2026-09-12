#!/usr/bin/env python3
"""Generate synthetic construction-site point cloud + mock BIM data for testing."""

import struct
import json
import math
import random
import sys
from pathlib import Path

random.seed(42)

SITES_DIR = Path(__file__).resolve().parents[1] / "data" / "sites"
BIM_DIR = Path(__file__).resolve().parents[1] / "data" / "bim"


def write_ply_binary(path: Path, vertices: list) -> None:
    """Write a binary little-endian PLY with vertex positions and colors."""
    n = len(vertices)
    header = f"""ply
format binary_little_endian 1.0
element vertex {n}
property float x
property float y
property float z
property uchar red
property uchar green
property uchar blue
end_header
"""
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        for x, y, z, r, g, b in vertices:
            f.write(struct.pack("<fffBBB", x, y, z, r, g, b))


# ── Scene parameters ──────────────────────────────────────────
# A roughly 20m x 15m room, +Z up, Y forward, X right

def gen_floor(w=20, d=15, spacing=0.1):
    pts = []
    x = -w / 2
    while x <= w / 2:
        z = -d / 2
        while z <= d / 2:
            # slight height variation
            y = -0.02 + random.uniform(-0.01, 0.01)
            pts.append((x, y, z, 140, 140, 140))
            z += spacing
        x += spacing
    return pts

def gen_wall(x0, y0, z0, w, h, spacing=0.08, color=(180, 170, 160)):
    pts = []
    x = x0
    while abs(x - x0) <= w:
        y = y0
        while y <= y0 + h:
            pts.append((x, y, z0, *color))
            y += spacing
        x += spacing
    return pts

def gen_column(cx, cz, h=3.0, radius=0.3, spacing=0.05, color=(200, 180, 150)):
    pts = []
    for angle in range(0, 360, 8):
        rad = math.radians(angle)
        x = cx + radius * math.cos(rad)
        z = cz + radius * math.sin(rad)
        y = 0
        while y <= h:
            pts.append((x, y, z, *color))
            y += spacing
    # fill interior roughly
    for y in [x * 0.1 for x in range(0, int(h / 0.1))]:
        for dx in [-0.1, 0, 0.1]:
            for dz in [-0.1, 0, 0.1]:
                pts.append((cx + dx, y, cz + dz, 190, 170, 140))
    return pts

def gen_rebar_cluster(cx, cz, count=20, h=1.2, color=(180, 80, 60)):
    """Vertical rebar sticks protruding from floor."""
    pts = []
    for _ in range(count):
        rx = cx + random.uniform(-0.3, 0.3)
        rz = cz + random.uniform(-0.3, 0.3)
        y = 0
        while y <= h + random.uniform(-0.1, 0.1):
            # slight lean
            lean_x = random.uniform(-0.01, 0.01) * (y / h)
            lean_z = random.uniform(-0.01, 0.01) * (y / h)
            pts.append((rx + lean_x, y, rz + lean_z, *color))
            y += 0.04
    return pts

def gen_pipe(cx, cz, length=2.0, radius=0.08, h_offset=1.8, color=(160, 140, 120)):
    """Horizontal pipe along X axis at a given height."""
    pts = []
    for angle in range(0, 360, 15):
        rad = math.radians(angle)
        r = radius * 1.2
        x = cx
        while x <= cx + length:
            y = h_offset + r * math.sin(rad)
            z = cz + r * math.cos(rad)
            pts.append((x, y, z, *color))
            x += 0.03
    return pts

def gen_opening(cx, cz, w=1.0, h=2.0, color=(100, 100, 100)):
    """Dark opening in wall - we just add sparse points at the edges."""
    pts = []
    for y in range(0, int(h / 0.1)):
        pts.append((cx, y * 0.1, cz, *color))
        pts.append((cx + w, y * 0.1, cz, *color))
    for x in range(0, int(w / 0.1)):
        pts.append((cx + x * 0.1, 0, cz, *color))
        pts.append((cx + x * 0.1, h, cz, *color))
    return pts


# ── Assemble scene ────────────────────────────────────────────
print("Generating construction scene...")
verts = []

# Floor
verts.extend(gen_floor())
print(f"  floor: {len(verts)} pts")

# Back wall (at z = -7.5, facing +Z)
verts.extend(gen_wall(-10, 0, -7.5, 20, 4.0, color=(170, 155, 140)))
print(f"  + back wall: {len(verts)} pts")

# Left wall (at x = -10, facing +X)
verts.extend(gen_wall(-10, 0, -7.5, 15, 4.0, color=(165, 150, 135)))
print(f"  + left wall: {len(verts)} pts")

# Right wall partial (at x = 10, facing -X)
verts.extend(gen_wall(10, 0, -7.5, 15, 4.0, color=(165, 150, 135)))
print(f"  + right wall: {len(verts)} pts")

# Column at (3, 0, -2)
verts.extend(gen_column(3.0, -2.0, h=4.0))
print(f"  + column: {len(verts)} pts")

# Column at (-4, 0, 3)
verts.extend(gen_column(-4.0, 3.0, h=4.0, radius=0.25, color=(210, 190, 160)))
print(f"  + column 2: {len(verts)} pts")

# Rebar cluster at (5, 0, 4)
verts.extend(gen_rebar_cluster(5.0, 4.0, count=25))
print(f"  + rebar: {len(verts)} pts")

# Another rebar cluster at (-5, 0, -4)
verts.extend(gen_rebar_cluster(-5.0, -4.0, count=15, color=(190, 90, 70)))
print(f"  + rebar 2: {len(verts)} pts")

# Pipe/conduit along ceiling
verts.extend(gen_pipe(2.0, -3.0, length=6.0, h_offset=3.2, color=(130, 120, 110)))
print(f"  + pipe: {len(verts)} pts")

# Door opening marker on back wall
verts.extend(gen_opening(-1.5, -7.48, w=1.2, h=2.1, color=(80, 80, 80)))
verts.extend(gen_opening(4.0, -7.48, w=1.5, h=2.4, color=(80, 80, 80)))
print(f"  + openings: {len(verts)} pts")

# Add some noise (sparse random points = dust/debris)
for _ in range(500):
    x = random.uniform(-10, 10)
    z = random.uniform(-7.5, 7.5)
    y = random.uniform(0, 3.5)
    c = random.choices([(180,160,140), (120,120,120), (100,100,80)], weights=[5,3,2])[0]
    verts.append((x, y, z, *c))
print(f"  + noise: {len(verts)} pts")

random.shuffle(verts)
print(f"  total: {len(verts)} vertices")

# Write PLY
out_dir = SITES_DIR / "test-site-01" / "20260911" / "raw"
out_dir.mkdir(parents=True, exist_ok=True)
ply_path = out_dir / "scan-01.ply"
write_ply_binary(ply_path, verts)
print(f"\nWrote {ply_path} ({ply_path.stat().st_size / 1024:.0f} KB)")

# ── Write meta.json ───────────────────────────────────────────
meta = {
    "site": "test-site-01",
    "date": "2026-09-11",
    "scanner": "iPhone 16 Pro (Polycam LiDAR)",
    "device": "iPhone 16 Pro",
    "notes": "Synthetic test data: mock construction site with columns, rebar, pipe, openings. No real site.",
    "coordinates": "local"
}
meta_path = SITES_DIR / "test-site-01" / "meta.json"
meta_path.write_text(json.dumps(meta, indent=2))
print(f"Wrote {meta_path}")


# ── Mock BIM objects ──────────────────────────────────────────
# In a real scenario these come from IFC. For testing, we define
# expected elements with name, type, position, dimensions.

bim_objects = [
    {
        "id": "col-01",
        "name": "Column A1",
        "ifc_type": "IfcColumn",
        "category": "structural",
        "position": {"x": 3.0, "y": 0.0, "z": -2.0},
        "dimensions": {"width": 0.6, "depth": 0.6, "height": 4.0},
        "material": "concrete"
    },
    {
        "id": "col-02",
        "name": "Column B2",
        "ifc_type": "IfcColumn",
        "category": "structural",
        "position": {"x": -4.0, "y": 0.0, "z": 3.0},
        "dimensions": {"width": 0.5, "depth": 0.5, "height": 4.0},
        "material": "concrete"
    },
    {
        "id": "rebar-01",
        "name": "Rebar Foundation Cluster A",
        "ifc_type": "IfcReinforcingBar",
        "category": "reinforcement",
        "position": {"x": 5.0, "y": 0.0, "z": 4.0},
        "dimensions": {"extent_x": 0.8, "extent_y": 1.2, "extent_z": 0.8},
        "material": "steel",
        "count": 25,
        "notes": "Vertical rebar protruding from foundation pour"
    },
    {
        "id": "rebar-02",
        "name": "Rebar Cluster B",
        "ifc_type": "IfcReinforcingBar",
        "category": "reinforcement",
        "position": {"x": -5.0, "y": 0.0, "z": -4.0},
        "dimensions": {"extent_x": 0.6, "extent_y": 1.0, "extent_z": 0.6},
        "material": "steel",
        "count": 15
    },
    {
        "id": "wall-01",
        "name": "Wall A (back)",
        "ifc_type": "IfcWall",
        "category": "architectural",
        "position": {"x": 0.0, "y": 0.0, "z": -7.5},
        "dimensions": {"width": 20.0, "height": 4.0, "thickness": 0.2},
        "material": "concrete",
        "openings": [
            {"type": "door", "position": {"x": -1.5, "z": -7.5}, "width": 1.2, "height": 2.1},
            {"type": "door", "position": {"x": 4.0, "z": -7.5}, "width": 1.5, "height": 2.4}
        ]
    },
    {
        "id": "wall-02",
        "name": "Wall B (left)",
        "ifc_type": "IfcWall",
        "category": "architectural",
        "position": {"x": -10.0, "y": 0.0, "z": 0.0},
        "dimensions": {"width": 15.0, "height": 4.0, "thickness": 0.2},
        "material": "concrete"
    },
    {
        "id": "wall-03",
        "name": "Wall C (right)",
        "ifc_type": "IfcWall",
        "category": "architectural",
        "position": {"x": 10.0, "y": 0.0, "z": 0.0},
        "dimensions": {"width": 15.0, "height": 4.0, "thickness": 0.2},
        "material": "concrete"
    },
    {
        "id": "pipe-01",
        "name": "Conduit Run 1",
        "ifc_type": "IfcPipeSegment",
        "category": "mechanical",
        "position": {"x": 2.0, "y": 3.2, "z": -3.0},
        "dimensions": {"length": 6.0, "diameter": 0.15},
        "material": "steel",
        "notes": "Overhead conduit, exposed"
    },
    {
        "id": "slab-01",
        "name": "Ground Floor Slab",
        "ifc_type": "IfcSlab",
        "category": "structural",
        "position": {"x": 0.0, "y": -0.15, "z": 0.0},
        "dimensions": {"width": 20.0, "depth": 15.0, "thickness": 0.3},
        "material": "concrete"
    }
]

bim_path = BIM_DIR / "test-site-01-bim.json"
BIM_DIR.mkdir(parents=True, exist_ok=True)
bim_path.write_text(json.dumps({
    "project": "Test Site 01",
    "source": "mock",
    "schema": "hyrolic-bim-v1",
    "objects": bim_objects
}, indent=2))
print(f"Wrote {bim_path}")

print("\nDone. Run: python3 ingest/ingest.py --site data/sites/test-site-01")
