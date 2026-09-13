#!/usr/bin/env python3
"""Train YOLO on construction site data (synthetic or real).

Fine-tunes YOLOv8n on labeled construction images to detect elements
like columns, walls, rebar, pipes, etc.

Usage:
    # Train on synthetic data (default)
    python3 backend/detection/train.py

    # Train on real concrete column dataset
    python3 backend/detection/train.py --data data/concrete-columns/dataset.yaml

    # Custom training
    python3 backend/detection/train.py --epochs 100 --model yolov8s.pt
"""

import argparse
import sys
from pathlib import Path

from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / 'data' / 'synthetic' / 'test-site-01' / 'dataset.yaml'


def train(epochs: int = 50, model_name: str = 'yolov8n.pt', imgsz: int = 640,
          dataset_path: str = None):
    """Fine-tune YOLO on construction site data.

    Args:
        epochs: Number of training epochs
        model_name: YOLO model variant (yolov8n.pt = nano, fastest)
        imgsz: Training image size (640 = YOLO default)
        dataset_path: Path to dataset.yaml (default: synthetic test site)
    """
    # Resolve dataset path
    ds_path = Path(dataset_path) if dataset_path else DEFAULT_DATASET
    if not ds_path.exists():
        print(f"Dataset config not found: {ds_path}", file=sys.stderr)
        sys.exit(1)

    # Model output dir lives alongside the dataset YAML
    model_dir = ds_path.parent / 'models'
    model_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading base model: {model_name}")
    model = YOLO(model_name)

    print(f"Training on {ds_path}")
    print(f"  Epochs: {epochs}")
    print(f"  Image size: {imgsz}")
    print(f"  Output: {model_dir}/")
    print()

    results = model.train(
        data=str(ds_path),
        epochs=epochs,
        imgsz=imgsz,
        project=str(model_dir),
        name='run',
        exist_ok=True,
        patience=20,           # Early stopping if no improvement
        batch=8,               # Small batch for Mac CPU
        workers=0,             # No multiprocessing on Mac
        device='cpu',          # CPU on Mac (MPS has issues)
        verbose=True,
    )

    # Find best weights
    best_weights = model_dir / 'run' / 'weights' / 'best.pt'
    last_weights = model_dir / 'run' / 'weights' / 'last.pt'

    if best_weights.exists():
        print(f"\nTraining complete!")
        print(f"  Best weights: {best_weights}")
        print(f"  Last weights: {last_weights}")
        print(f"\nTo run detection:")
        print(f"  python3 backend/detection/detect.py --model {best_weights}")
    else:
        print(f"\nTraining finished but best.pt not found at {best_weights}")
        print(f"Check {model_dir}/run/ for results.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--epochs', type=int, default=50,
                    help='Number of training epochs (default: 50)')
    ap.add_argument('--model', default='yolov8n.pt',
                    help='Base YOLO model (default: yolov8n.pt)')
    ap.add_argument('--imgsz', type=int, default=640,
                    help='Training image size (default: 640)')
    ap.add_argument('--data', type=str, default=None,
                    help='Path to dataset.yaml (default: synthetic test site)')
    args = ap.parse_args()

    train(epochs=args.epochs, model_name=args.model,
          imgsz=args.imgsz, dataset_path=args.data)


if __name__ == '__main__':
    main()
