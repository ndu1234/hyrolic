#!/usr/bin/env python3
"""Render synthetic camera frames from the test PLY scene for YOLO training.

Recreates the construction scene as solid 3D geometry (not just points) and
renders RGB + depth images from simulated Go2 X walkthrough viewpoints.

Uses pyrender (trimesh + pyglet/osmesa) for headless rendering, which works
on macOS without a display.

Output (per render run):
  data/synthetic/test-site-01/
    renders/
      frame_0000.jpg       # RGB image (1280x720)
      frame_0000_depth.png # Depth map (16-bit PNG, millimeters)
      frame_0001.jpg
      frame_0001_depth.png
      ...
    camera_poses.json      # Camera intrinsics + extrinsics per frame

Usage:
    python3 backend/ingest/render_synthetic_frames.py
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np

# ── Rendering backend ───────────────────────────────────���────
# Try pyrender first (headless-friendly), fall back to trimesh's built-in
try:
    import pyrender
    import trimesh
    HAS_PYRENDER = True
except ImportError:
    print("pyrender + trimesh required. Install: pip install pyrender trimesh", file=sys.stderr)
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
PLY_PATH = REPO_ROOT / "data" / "sites" / "test-site-01" / "20260911" / "raw" / "scan-01.ply"
OUT_DIR = REPO_ROOT / "data" / "synthetic" / "test-site-01" / "renders"

# ── Camera intrinsics (Go2 X HD camera) ───────────────────────
# Specs: 1280x720 resolution, 120° horizontal FOV
WIDTH, HEIGHT = 1280, 720
HFOV_DEG = 120.0  # Go2 X wide-angle camera spec

# Focal length in pixels: f = (w/2) / tan(FOV/2)
FOCAL_X = (WIDTH / 2) / math.tan(math.radians(HFOV_DEG / 2))
FOCAL_Y = FOCAL_X  # Assume square pixels
CX = WIDTH / 2
CY = HEIGHT / 2

# Pyrender camera: yfov is vertical FOV. Compute from aspect ratio and HFOV.
# HFOV = 2 * atan(tan(VFOV/2) * aspect)
# So VFOV = 2 * atan(tan(HFOV/2) / aspect)
ASPECT = WIDTH / HEIGHT
VFOV_RAD = 2 * math.atan(math.tan(math.radians(HFOV_DEG / 2)) / ASPECT)


def make_camera_pose(eye: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Create a 4x4 camera extrinsics matrix.

    Pyrender uses OpenCV convention: camera looks along -Z in camera space,
    with +X right and +Y up.

    Args:
        eye: Camera position in world coords [x, y, z]
        target: Point the camera is looking at

    Returns:
        4x4 camera-to-world transformation matrix
    """
    # Forward vector: from eye to target (this will be -Z in camera space)
    forward = target - eye
    forward_norm = np.linalg.norm(forward)
    if forward_norm < 1e-8:
        forward = np.array([0.0, 0.0, 1.0])
    else:
        forward = forward / forward_norm

    # World up vector
    world_up = np.array([0.0, 1.0, 0.0])

    # Right vector: cross of forward and world up
    right = np.cross(forward, world_up)
    right_norm = np.linalg.norm(right)
    if right_norm < 1e-8:
        # Forward is parallel to world up — use Z as right
        right = np.array([0.0, 0.0, 1.0])
    else:
        right = right / right_norm

    # True up: cross of right and forward
    up = np.cross(right, forward)
    up = up / np.linalg.norm(up)

    # Build rotation matrix (camera-to-world)
    R = np.column_stack([right, up, -forward])

    # Build 4x4 camera-to-world matrix
    pose = np.eye(4)
    pose[:3, :3] = R
    pose[:3, 3] = eye

    return pose


def build_scene_meshes() -> list:
    """Build the synthetic construction scene as trimesh/pyrender mesh objects.

    Creates solid 3D geometry that mirrors the PLY point cloud scene from
    generate_test_data.py but renders actual surfaces for realistic images.
    """
    meshes = []

    # ── Floor slab ────────────────────────────────────────
    # 20m x 15m x 0.02m slab at y=-0.02
    floor = trimesh.creation.box(extents=[20.0, 0.02, 15.0])
    floor.apply_translation([0.0, -0.02, 0.0])
    floor.visual.vertex_colors = np.array([140, 140, 140, 255], dtype=np.uint8)
    meshes.append(floor)

    # ── Back wall (at z=-7.5) ─────────────────────────────
    # 20m wide, 4m tall, 0.2m thick
    back_wall = trimesh.creation.box(extents=[20.0, 4.0, 0.2])
    back_wall.apply_translation([0.0, 2.0, -7.5])
    back_wall.visual.vertex_colors = np.array([170, 155, 140, 255], dtype=np.uint8)
    meshes.append(back_wall)

    # ── Left wall (at x=-10) ──────────────────────────────
    left_wall = trimesh.creation.box(extents=[0.2, 4.0, 15.0])
    left_wall.apply_translation([-10.0, 2.0, 0.0])
    left_wall.visual.vertex_colors = np.array([165, 150, 135, 255], dtype=np.uint8)
    meshes.append(left_wall)

    # ── Right wall (at x=10) ──────────────────────────────
    right_wall = trimesh.creation.box(extents=[0.2, 4.0, 15.0])
    right_wall.apply_translation([10.0, 2.0, 0.0])
    right_wall.visual.vertex_colors = np.array([165, 150, 135, 255], dtype=np.uint8)
    meshes.append(right_wall)

    # ── Column 1 (at x=3, z=-2) ───────────────────────────
    # Cylinder: radius 0.3m, height 4m
    col1 = trimesh.creation.cylinder(radius=0.3, height=4.0, sections=32)
    col1.apply_translation([3.0, 2.0, -2.0])
    col1.visual.vertex_colors = np.array([200, 180, 150, 255], dtype=np.uint8)
    meshes.append(col1)

    # ── Column 2 (at x=-4, z=3) ──────────────────────────
    col2 = trimesh.creation.cylinder(radius=0.25, height=4.0, sections=32)
    col2.apply_translation([-4.0, 2.0, 3.0])
    col2.visual.vertex_colors = np.array([210, 190, 160, 255], dtype=np.uint8)
    meshes.append(col2)

    # ── Rebar cluster 1 (at x=5, z=4) ─────────────────────
    # 25 thin vertical cylinders, slightly randomized positions
    for i in range(25):
        rx = 5.0 + np.random.uniform(-0.3, 0.3)
        rz = 4.0 + np.random.uniform(-0.3, 0.3)
        h = 1.2 + np.random.uniform(-0.1, 0.1)
        rebar = trimesh.creation.cylinder(radius=0.015, height=h, sections=8)
        # Slight random lean
        lean_x = np.random.uniform(-0.02, 0.02) * (h / 1.2)
        lean_z = np.random.uniform(-0.02, 0.02) * (h / 1.2)
        rebar.apply_translation([rx + lean_x, h/2, rz + lean_z])
        rebar.visual.vertex_colors = np.array([180, 80, 60, 255], dtype=np.uint8)
        meshes.append(rebar)

    # ── Rebar cluster 2 (at x=-5, z=-4) ───────────────────
    for i in range(15):
        rx = -5.0 + np.random.uniform(-0.3, 0.3)
        rz = -4.0 + np.random.uniform(-0.3, 0.3)
        h = 1.0 + np.random.uniform(-0.1, 0.1)
        rebar = trimesh.creation.cylinder(radius=0.015, height=h, sections=8)
        lean_x = np.random.uniform(-0.02, 0.02) * (h / 1.0)
        lean_z = np.random.uniform(-0.02, 0.02) * (h / 1.0)
        rebar.apply_translation([rx + lean_x, h/2, rz + lean_z])
        rebar.visual.vertex_colors = np.array([190, 90, 70, 255], dtype=np.uint8)
        meshes.append(rebar)

    # ── Overhead conduit (pipe) ────────────────────────────
    # Horizontal cylinder along X axis at y=3.2
    pipe = trimesh.creation.cylinder(radius=0.08, height=6.0, sections=16)
    pipe.apply_translation([5.0, 3.2, -3.0])
    pipe.visual.vertex_colors = np.array([130, 120, 110, 255], dtype=np.uint8)
    meshes.append(pipe)

    print(f"  Scene built: {len(meshes)} mesh primitives")
    return meshes


def define_camera_path() -> list:
    """Define a walkthrough path around the construction site.

    Returns a list of (eye, target) tuples simulating a robot walking
    around the room at ~1.5m eye height, stopping at waypoints.

    Path: enter at left → walk along back wall → right side → center → exit
    """
    path = [
        # Start at entrance, looking at center
        (np.array([-8.0, 1.5, -6.0]), np.array([0.0, 1.5, 0.0])),
        # Move toward column 1
        (np.array([-2.0, 1.5, -6.0]), np.array([3.0, 1.5, -2.0])),
        # Close-up of column 1
        (np.array([2.0, 1.5, -5.0]), np.array([3.0, 1.5, -2.0])),
        # Back wall, looking at rebar cluster
        (np.array([4.0, 1.5, -6.5]), np.array([5.0, 1.5, 4.0])),
        # Right side, looking across
        (np.array([8.0, 1.5, -3.0]), np.array([-2.0, 1.5, 1.0])),
        # Center back, wide shot
        (np.array([0.0, 1.5, -6.5]), np.array([0.0, 1.5, 0.0])),
        # Left side, looking at column 2
        (np.array([-6.0, 1.5, -1.0]), np.array([-4.0, 1.5, 3.0])),
        # Close-up of rebar cluster 2
        (np.array([-6.0, 1.5, -3.0]), np.array([-5.0, 1.5, -4.0])),
        # Far left corner
        (np.array([-8.0, 1.5, 3.0]), np.array([-3.0, 1.5, 0.0])),
        # Center, overview
        (np.array([3.0, 2.0, 2.0]), np.array([0.0, 1.5, -1.0])),
        # Exit
        (np.array([-7.0, 1.5, 5.0]), np.array([-2.0, 1.5, 2.0])),
    ]
    print(f"  Camera path: {len(path)} waypoints")
    return path


def render_frames(meshes: list, camera_path: list) -> dict:
    """Render RGB + depth frames from each camera pose using pyrender.

    Args:
        meshes: List of trimesh objects (will be converted to pyrender meshes)
        camera_path: List of (eye, target) tuples

    Returns:
        Dict mapping frame index to camera pose data
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create pyrender scene
    scene = pyrender.Scene(ambient_light=np.array([0.3, 0.3, 0.3, 1.0]))

    # Add all meshes to the scene
    for i, mesh in enumerate(meshes):
        # Convert trimesh to pyrender mesh
        # Use smooth=False to preserve vertex colors
        render_mesh = pyrender.Mesh.from_trimesh(mesh, smooth=False)
        scene.add_node(pyrender.Node(mesh=render_mesh, name=f"mesh_{i}"))

    # Add lighting — directional light from above-right
    light = pyrender.DirectionalLight(color=np.ones(3), intensity=2.0)
    light_pose = np.eye(4)
    light_pose[:3, 3] = [5.0, 10.0, 5.0]
    scene.add_node(pyrender.Node(light=light, matrix=light_pose))

    # Add fill light from left
    fill = pyrender.DirectionalLight(color=np.ones(3) * 0.6, intensity=1.0)
    fill_pose = np.eye(4)
    fill_pose[:3, 3] = [-8.0, 5.0, 0.0]
    scene.add_node(pyrender.Node(light=fill, matrix=fill_pose))

    # Create renderer with offscreen support
    r = pyrender.OffscreenRenderer(WIDTH, HEIGHT)

    camera_poses = {}

    for idx, (eye, target) in enumerate(camera_path):
        # Compute camera pose
        pose = make_camera_pose(eye, target)

        # Set camera in the scene
        camera = pyrender.PerspectiveCamera(yfov=VFOV_RAD, aspectRatio=ASPECT)
        scene.add_node(pyrender.Node(camera=camera, matrix=pose))

        # Render RGB
        rgb, depth = r.render(scene)

        # Save RGB as JPEG
        rgb_path = OUT_DIR / f"frame_{idx:04d}.jpg"
        from PIL import Image
        Image.fromarray(rgb).save(rgb_path, quality=95)

        # Save depth as 16-bit PNG (values in millimeters)
        # depth array contains distances from camera in meters
        depth_mm = (depth * 1000).astype(np.uint16)
        depth_path = OUT_DIR / f"frame_{idx:04d}_depth.png"
        Image.fromarray(depth_mm).save(depth_path)

        # Store camera pose data
        camera_poses[f"frame_{idx:04d}"] = {
            "eye": eye.tolist(),
            "target": target.tolist(),
            "extrinsics": pose.tolist(),
            "intrinsics": {
                "width": WIDTH,
                "height": HEIGHT,
                "fx": round(FOCAL_X, 2),
                "fy": round(FOCAL_Y, 2),
                "cx": CX,
                "cy": CY,
                "hfov_deg": HFOV_DEG,
                "vfov_deg": round(math.degrees(VFOV_RAD), 2)
            }
        }

        # Remove camera node for next frame (keep meshes)
        scene.remove_node(scene.main_camera_node)

        print(f"  frame_{idx:04d}: eye=({eye[0]:.1f}, {eye[1]:.1f}, {eye[2]:.1f}) "
              f"target=({target[0]:.1f}, {target[1]:.1f}, {target[2]:.1f})")

    return camera_poses


def main():
    print("Synthetic camera frame renderer for Hyrolic")
    print("─" * 50)

    # Set random seed for reproducible rebar placement
    np.random.seed(42)

    print("Building scene geometry...")
    meshes = build_scene_meshes()

    print("Defining camera path...")
    camera_path = define_camera_path()

    print("Rendering frames...")
    camera_poses = render_frames(meshes, camera_path)

    # ── Write camera poses JSON ──────────────────────────────
    poses_path = OUT_DIR.parent / "camera_poses.json"
    with open(poses_path, "w") as f:
        json.dump({
            "scene": "test-site-01",
            "sensor": "Go2 X HD Camera (simulated)",
            "num_frames": len(camera_poses),
            "frames": camera_poses
        }, f, indent=2)
    print(f"  Wrote {poses_path}")

    # ── Summary ──────────────────────────────────────────────
    total_rgb = len(list(OUT_DIR.glob("frame_*.jpg")))
    total_depth = len(list(OUT_DIR.glob("frame_*_depth.png")))
    print(f"\nDone: {total_rgb} RGB frames, {total_depth} depth maps")
    print(f"  Output: {OUT_DIR}/")
    print(f"  Poses: {poses_path}")


if __name__ == "__main__":
    main()
