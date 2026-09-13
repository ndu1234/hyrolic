#!/usr/bin/env python3
"""YOLO detection pipeline — runs inference on camera frames.

On Mac: loads synthetic frames from disk, runs YOLOv8 via PyTorch.
On Jetson: (future) loads live frames from Go2 X, runs YOLO via TensorRT.

Output (per run):
  data/synthetic/test-site-01/detections/
    detections.json      # All detections across all frames
    frame_0000.jpg       # Debug: frame with bounding boxes drawn

Usage:
    python3 backend/detection/detect.py
    python3 backend/detection/detect.py --scene test-site-01 --model yolov8n.pt
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

# ── YOLO import ───────────────────────────────────────────────
# On Mac: ultralytics. On Jetson: will be replaced by TensorRT version.
try:
    from ultralytics import YOLO
except ImportError:
    print("ultralytics not installed. Run: pip install ultralytics", file=sys.stderr)
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_DIR = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'renders'
POSES_PATH = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'camera_poses.json'
OUT_DIR = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'detections'

# ── Class names (must match label.py) ─────────────────────────
CLASS_NAMES = ['column', 'wall', 'rebar', 'pipe', 'slab', 'opening']


def load_frames() -> list:
    """Load all rendered frame paths sorted by index."""
    frames = sorted(RENDER_DIR.glob("frame_*.jpg"))
    if not frames:
        print(f"No frames found in {RENDER_DIR}", file=sys.stderr)
        print("Run: python3 backend/ingest/render_synthetic_frames.py", file=sys.stderr)
        sys.exit(1)
    return frames


def load_camera_poses() -> dict:
    """Load camera poses for each frame."""
    with open(POSES_PATH) as f:
        return json.load(f)


def run_inference(model_path: str = 'yolov8n.pt', conf_thresh: float = 0.25):
    """Run YOLO inference on all synthetic frames.

    Args:
        model_path: Path to YOLO weights file or model name
        conf_thresh: Confidence threshold for detections (0-1)
    """
    print(f"Loading YOLO model: {model_path}")
    model = YOLO(model_path)

    # Check if the model knows our classes
    # A COCO-pretrained model won't know 'column', 'wall', etc.
    # We'll detect generic objects and note the class mismatch
    model_names = model.names
    print(f"  Model classes ({len(model_names)}): {list(model_names.values())[:10]}...")

    frames = load_frames()
    poses_data = load_camera_poses()
    print(f"  Frames to process: {len(frames)}")

    # Create output directory
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_detections = []

    for idx, frame_path in enumerate(frames):
        # Load image
        img = cv2.imread(str(frame_path))
        if img is None:
            print(f"  WARNING: Could not read {frame_path}", file=sys.stderr)
            continue

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Run YOLO inference
        results = model(img_rgb, conf=conf_thresh, verbose=False)

        # Get camera pose for this frame (for later 3D projection)
        frame_key = frame_path.stem
        frame_pose = poses_data.get('frames', {}).get(frame_key, {})
        extrinsics = np.array(frame_pose.get('extrinsics', np.eye(4)))

        # Process detections
        frame_detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = model_names.get(cls_id, f"class_{cls_id}")

                detection = {
                    'frame': frame_key,
                    'bbox': [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    'confidence': round(conf, 3),
                    'class_id': cls_id,
                    'class_name': cls_name,
                    'center_2d': [
                        round((x1 + x2) / 2, 1),
                        round((y1 + y2) / 2, 1)
                    ]
                }
                frame_detections.append(detection)

        all_detections.extend(frame_detections)

        # Draw detections on debug image
        debug_img = img.copy()
        for det in frame_detections:
            x1, y1, x2, y2 = [int(v) for v in det['bbox']]
            color = (0, 255, 0)  # green
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)
            label = f"{det['class_name']} {det['confidence']:.2f}"
            cv2.putText(debug_img, label, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        debug_path = OUT_DIR / frame_path.name
        cv2.imwrite(str(debug_path), debug_img)

        if (idx + 1) % 5 == 0 or idx == len(frames) - 1:
            print(f"  Processed {idx + 1}/{len(frames)} — "
                  f"{len(frame_detections)} detections in this frame")

    # ── Write all detections to JSON ──────────────────────────
    detections_path = OUT_DIR / 'detections.json'
    output = {
        'model': model_path,
        'num_frames': len(frames),
        'total_detections': len(all_detections),
        'classes_used': sorted(set(d['class_name'] for d in all_detections)),
        'detections': all_detections
    }
    with open(detections_path, 'w') as f:
        json.dump(output, f, indent=2)

    # ── Summary ───────────────────────────────────────────────
    print(f"\nDone: {len(all_detections)} detections across {len(frames)} frames")
    print(f"  Classes found: {output['classes_used']}")
    print(f"  Detections JSON: {detections_path}")
    print(f"  Debug frames: {OUT_DIR}/")

    # Show per-class counts
    from collections import Counter
    counts = Counter(d['class_name'] for d in all_detections)
    for cls_name, count in counts.most_common():
        print(f"    {cls_name}: {count}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model', default='yolov8n.pt',
                    help='YOLO model path or name (default: yolov8n.pt)')
    ap.add_argument('--scene', default='test-site-01',
                    help='Scene name (default: test-site-01)')
    ap.add_argument('--conf', type=float, default=0.25,
                    help='Confidence threshold (default: 0.25)')
    args = ap.parse_args()

    run_inference(model_path=args.model, conf_thresh=args.conf)


if __name__ == '__main__':
    main()
