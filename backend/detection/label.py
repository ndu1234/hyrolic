#!/usr/bin/env python3
"""Generate YOLO-format labels from BIM objects + camera poses.

Projects 3D BIM objects into 2D bounding boxes on each synthetic camera frame
using the known camera intrinsics and extrinsics. This creates ground-truth
labels for training YOLO to detect construction elements.

YOLO label format (per frame):
    class_id cx cy w h
    (all normalized 0-1, one line per object)

Output:
    data/synthetic/test-site-01/labels/
        frame_0000.txt
        frame_0001.txt
        ...
    data/synthetic/test-site-01/dataset.yaml   # YOLO dataset config

Classes:
    0: column
    1: wall
    2: rebar
    3: pipe
    4: slab
    5: opening

Usage:
    python3 backend/detection/label.py
"""

import json
from pathlib import Path

import numpy as np

# ── Paths ─────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
BIM_PATH = REPO_ROOT / 'data' / 'bim' / 'test-site-01-bim.json'
POSES_PATH = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'camera_poses.json'
LABEL_DIR = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'labels'
DATASET_YAML = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'dataset.yaml'

# ── Class mapping: BIM object type → YOLO class ID ────────────
CLASS_MAP = {
    'structural': 0,      # columns, slabs
    'architectural': 1,   # walls
    'reinforcement': 2,   # rebar
    'mechanical': 3,      # pipes, conduit
}
CLASS_NAMES = ['column', 'wall', 'rebar', 'pipe', 'slab', 'opening']


def get_3d_bbox_corners(obj: dict) -> np.ndarray:
    """
    Get the 8 corners of a BIM object's bounding box in world coordinates.

    Returns: (8, 3) array of [x, y, z] corner positions.
    Corners are in the order:
        front-bottom-left, front-bottom-right, front-top-right, front-top-left,
        back-bottom-left, back-bottom-right, back-top-right, back-top-left
    """
    pos = obj['position']
    dims = obj.get('dimensions', {})

    # Each BIM object stores position as center, and dimensions as width/depth/height
    # or length/diameter for pipes
    if obj.get('ifc_type') == 'IfcPipeSegment':
        # Pipe: horizontal cylinder along X, approximate with a box
        w = dims.get('length', 1.0)
        h = dims.get('diameter', 0.15) * 2  # approximate box height
        d = h  # same for depth (cylindrical)
    elif obj.get('ifc_type') == 'IfcReinforcingBar':
        # Rebar clusters: already have extent dimensions
        w = dims.get('extent_x', 0.5)
        h = dims.get('extent_y', 1.0)
        d = dims.get('extent_z', 0.5)
    else:
        # Standard boxes: width (X), height (Y), depth (Z) or thickness
        w = dims.get('width', 0.5) or dims.get('thickness', 0.2)
        h = dims.get('height', 1.0) or dims.get('diameter', 0.5)
        d = dims.get('depth', 0.5) or dims.get('thickness', 0.2)

    # Half-extents
    hx, hy, hz = w / 2, h / 2, d / 2

    # 8 corners relative to center
    corners_rel = np.array([
        [-hx, -hy, -hz], [ hx, -hy, -hz], [ hx,  hy, -hz], [-hx,  hy, -hz],
        [-hx, -hy,  hz], [ hx, -hy,  hz], [ hx,  hy,  hz], [-hx,  hy,  hz],
    ])

    # Translate to world position
    cx, cy, cz = pos['x'], pos.get('y', 0), pos['z']
    return corners_rel + np.array([cx, cy, cz])


def project_to_2d(points_3d: np.ndarray, extrinsics: np.ndarray, intrinsics: dict) -> np.ndarray:
    """
    Project 3D world points to 2D image coordinates.

    Uses the pinhole camera model: x = K * [R|t] * X

    Args:
        points_3d: (N, 3) array of 3D points in world coordinates
        extrinsics: 4x4 camera-to-world matrix (from camera_poses.json)
        intrinsics: dict with fx, fy, cx, cy

    Returns:
        (N, 2) array of 2D pixel coordinates [u, v]
    """
    # Convert extrinsics from camera-to-world to world-to-camera
    # The stored matrix is the camera pose (camera-to-world)
    # We need world-to-camera: R^T and -R^T * t
    R = extrinsics[:3, :3]  # camera-to-world rotation
    t = extrinsics[:3, 3]   # camera position in world

    # World-to-camera transform
    R_w2c = R.T
    t_w2c = -R_w2c @ t

    # Transform points to camera space
    # X_cam = R_w2c * X_world + t_w2c
    pts_cam = (R_w2c @ points_3d.T).T + t_w2c

    # Pyrender camera looks along -Z, so negate Z to get standard depth (positive = front)
    pts_cam[:, 2] = -pts_cam[:, 2]

    # Filter points behind the camera (z <= 0)
    # Project only points with positive depth
    fx = float(intrinsics['fx'])
    fy = float(intrinsics['fy'])
    cx = float(intrinsics['cx'])
    cy = float(intrinsics['cy'])

    # Perspective projection
    u = fx * pts_cam[:, 0] / pts_cam[:, 2] + cx
    v = fy * pts_cam[:, 1] / pts_cam[:, 2] + cy

    return np.column_stack([u, v]), pts_cam[:, 2]


def generate_labels():
    """Generate YOLO labels for all synthetic camera frames."""
    # Load BIM objects
    with open(BIM_PATH) as f:
        bim_data = json.load(f)
    bim_objects = bim_data['objects']

    # Load camera poses
    with open(POSES_PATH) as f:
        poses_data = json.load(f)

    # Create label output directory
    LABEL_DIR.mkdir(parents=True, exist_ok=True)

    # Track statistics
    total_labels = 0
    frame_counts = []

    # Process each frame
    for frame_key, frame_data in poses_data['frames'].items():
        extrinsics = np.array(frame_data['extrinsics'])
        intrinsics = frame_data['intrinsics']
        width = int(intrinsics['width'])
        height = int(intrinsics['height'])

        labels = []

        # Project each BIM object into this frame
        for obj in bim_objects:
            # Determine class ID from category
            cat = obj.get('category', '')
            class_id = CLASS_MAP.get(cat)
            if class_id is None:
                continue  # Skip unknown categories

            # Get 3D bounding box corners
            corners_3d = get_3d_bbox_corners(obj)

            # Project to 2D
            pts_2d, depths = project_to_2d(corners_3d, extrinsics, intrinsics)

            # Skip if ALL corners are behind the camera
            if np.all(depths <= 0):
                continue

            # Get 2D bounding box (only from corners in front of camera)
            valid = depths > 0
            if valid.sum() < 3:
                continue  # Need at least 3 corners for a stable box

            valid_pts = pts_2d[valid]
            x_min = max(0, valid_pts[:, 0].min())
            y_min = max(0, valid_pts[:, 1].min())
            x_max = min(width, valid_pts[:, 0].max())
            y_max = min(height, valid_pts[:, 1].max())

            # Skip if box is too small (noise) or outside frame
            box_w = x_max - x_min
            box_h = y_max - y_min
            if box_w < 3 or box_h < 3:
                continue

            # YOLO format: class_id cx cy w h (normalized 0-1)
            cx = (x_min + x_max) / 2 / width
            cy = (y_min + y_max) / 2 / height
            nw = box_w / width
            nh = box_h / height

            # Clamp to [0, 1]
            cx = min(1.0, max(0.0, cx))
            cy = min(1.0, max(0.0, cy))
            nw = min(1.0, max(0.0, nw))
            nh = min(1.0, max(0.0, nh))

            labels.append(f"{class_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        # Write label file
        label_path = LABEL_DIR / f"{frame_key}.txt"
        label_path.write_text('\n'.join(labels) + '\n' if labels else '')
        total_labels += len(labels)
        frame_counts.append(len(labels))

    # ── Create YOLO dataset YAML ──────────────────────────────
    # Points to the images directory (labels live in sibling labels/)
    images_dir_abs = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'images'

    dataset_yaml_content = f"""
# Hyrolic synthetic dataset — auto-generated by label.py
# YOLOv8 dataset config

train: {images_dir_abs}
val: {images_dir_abs}

nc: {len(CLASS_NAMES)}
names: {CLASS_NAMES}
"""
    DATASET_YAML.write_text(dataset_yaml_content.strip())

    # ── Summary ───────────────────────────────────────────────
    print(f"Labels generated: {total_labels} total across {len(frame_counts)} frames")
    print(f"  Frames with labels: {sum(1 for c in frame_counts if c > 0)}/{len(frame_counts)}")
    print(f"  Avg labels per frame: {np.mean(frame_counts):.1f}")
    print(f"  Label dir: {LABEL_DIR}")
    print(f"  Dataset YAML: {DATASET_YAML}")
    print(f"\nClasses: {', '.join(CLASS_NAMES)}")


if __name__ == '__main__':
    generate_labels()