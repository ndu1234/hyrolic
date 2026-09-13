#!/usr/bin/env python3
"""Train YOLO on synthetic construction site data.

Fine-tunes YOLOv8n on our labeled synthetic frames so it learns to detect
columns, walls, rebar, pipes, slabs, and openings.

Usage:
    python3 backend/detection/train.py
    python3 backend/detection/train.py --epochs 50 --model yolov8n.pt
"""

import argparse
import sys
from pathlib import Path

from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_YAML = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'dataset.yaml'
MODEL_DIR = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'models'


def train(epochs: int = 50, model_name: str = 'yolov8n.pt', imgsz: int = 640):
    """Fine-tune YOLO on synthetic construction data.

    Args:
        epochs: Number of training epochs (50 is plenty for 11 images)
        model_name: YOLO model variant (yolov8n.pt = nano, fastest)
        imgsz: Training image size (640 = YOLO default)
    """
    if not DATASET_YAML.exists():
        print(f"Dataset config not found: {DATASET_YAML}", file=sys.stderr)
        print("Run: python3 backend/detection/label.py", file=sys.stderr)
        sys.exit(1)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading base model: {model_name}")
    model = YOLO(model_name)

    print(f"Training on {DATASET_YAML}")
    print(f"  Epochs: {epochs}")
    print(f"  Image size: {imgsz}")
    print(f"  Output: {MODEL_DIR}/")
    print()

    results = model.train(
        data=str(DATASET_YAML),
        epochs=epochs,
        imgsz=imgsz,
        project=str(MODEL_DIR),
        name='run',
        exist_ok=True,
        patience=20,           # Early stopping if no improvement
        batch=4,               # Small batch for Mac CPU/GPU
        workers=0,             # No multiprocessing on Mac
        device='cpu',          # Force CPU on Mac (GPU may not work with PyTorch + MPS)
        verbose=True,
    )

    # Find the best weights
    best_weights = MODEL_DIR / 'run' / 'weights' / 'best.pt'
    last_weights = MODEL_DIR / 'run' / 'weights' / 'last.pt'

    if best_weights.exists():
        print(f"\nTraining complete!")
        print(f"  Best weights: {best_weights}")
        print(f"  Last weights: {last_weights}")
        print(f"\nTo run detection with the trained model:")
        print(f"  python3 backend/detection/detect.py --model {best_weights}")
    else:
        print(f"\nTraining finished but best.pt not found at {best_weights}")
        print(f"Check {MODEL_DIR}/run/ for results.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--epochs', type=int, default=50,
                    help='Number of training epochs (default: 50)')
    ap.add_argument('--model', default='yolov8n.pt',
                    help='Base YOLO model (default: yolov8n.pt)')
    ap.add_argument('--imgsz', type=int, default=640,
                    help='Training image size (default: 640)')
    args = ap.parse_args()

    train(epochs=args.epochs, model_name=args.model, imgsz=args.imgsz)


if __name__ == '__main__':
    main()
