"""Frame loader — loads camera frames from disk (Mac dev mode).

On Jetson, this will be replaced by a live camera feed from the Go2 X.
For now, loads synthetic rendered frames + camera poses.

Usage:
    from backend.ingest.frame_loader import FrameLoader

    loader = FrameLoader(scene='test-site-01')
    for frame in loader:
        # frame.rgb: numpy array (H, W, 3)
        # frame.depth: numpy array (H, W) in millimeters
        # frame.pose: 4x4 camera extrinsics matrix
        # frame.intrinsics: dict with fx, fy, cx, cy
        print(f"Loaded {frame.filename}")
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# ── Path resolution (works from repo root or anywhere) ─────────
# This script lives at backend/ingest/frame_loader.py
# Repo root = parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _synthetic_dir() -> Path:
    return _REPO_ROOT / 'data' / 'synthetic'


@dataclass
class Frame:
    """A single camera frame with metadata."""
    filename: str
    idx: int
    rgb: np.ndarray          # (H, W, 3) uint8, RGB order
    depth: np.ndarray        # (H, W) uint16, values in millimeters
    pose: np.ndarray         # 4x4 camera extrinsics (camera-to-world)
    intrinsics: dict         # fx, fy, cx, cy, hfov, vfov


class FrameLoader:
    """Loads synthetic rendered frames from disk.

    Iterates over all frames in a scene's renders/ directory and yields
    Frame objects with RGB, depth, camera pose, and intrinsics.

    Args:
        scene: Scene name (subfolder under data/synthetic/)
    """

    def __init__(self, scene: str = 'test-site-01'):
        self.render_dir = _synthetic_dir() / scene / 'renders'
        self.poses_path = _synthetic_dir() / scene / 'camera_poses.json'

        # Load camera poses from JSON
        if not self.poses_path.exists():
            raise FileNotFoundError(
                f"No camera_poses.json found at {self.poses_path}\n"
                f"Run: python3 backend/ingest/render_synthetic_frames.py"
            )
        with open(self.poses_path) as f:
            self.poses_data = json.load(f)

        # Discover all frame files, sorted by index
        self.frame_files = sorted(self.render_dir.glob("frame_*.jpg"))
        if not self.frame_files:
            raise FileNotFoundError(
                f"No rendered frames found at {self.render_dir}\n"
                f"Run: python3 backend/ingest/render_synthetic_frames.py"
            )

        print(f"[FrameLoader] Loaded {len(self.frame_files)} frames from '{scene}'")

    def __len__(self) -> int:
        """Total number of frames available."""
        return len(self.frame_files)

    def __iter__(self):
        """Iterate over all frames in order (lazy load)."""
        for idx, rgb_path in enumerate(self.frame_files):
            yield self._load_frame(rgb_path, idx)

    def __getitem__(self, idx: int):
        """Load a specific frame by index (0-based)."""
        if idx < 0 or idx >= len(self.frame_files):
            raise IndexError(f"Frame index {idx} out of range (0-{len(self.frame_files)-1})")
        return self._load_frame(self.frame_files[idx], idx)

    def _load_frame(self, rgb_path: Path, idx: int) -> Frame:
        """
        Load RGB image, depth map, and camera pose for a single frame.

        Depth map file: same stem as RGB with '_depth.png' suffix.
        Camera pose: looked up by frame key in the poses JSON.
        """
        # RGB: convert to numpy array (H, W, 3) uint8
        rgb = np.array(Image.open(rgb_path).convert('RGB'))

        # Depth: same path pattern, replace .jpg with _depth.png
        depth_path = rgb_path.with_name(rgb_path.stem + '_depth.png')
        if depth_path.exists():
            depth = np.array(Image.open(depth_path)).astype(np.uint16)
        else:
            depth = np.zeros((rgb.shape[0], rgb.shape[1]), dtype=np.uint16)

        # Camera pose and intrinsics from the JSON manifest
        frame_key = rgb_path.stem  # e.g. "frame_0000"
        frame_data = self.poses_data.get('frames', {}).get(frame_key, {})
        pose = np.array(frame_data.get('extrinsics', np.eye(4).tolist()))
        intrinsics = frame_data.get('intrinsics', {})

        return Frame(
            filename=rgb_path.name,
            idx=idx,
            rgb=rgb,
            depth=depth,
            pose=pose,
            intrinsics=intrinsics
        )

    def summary(self) -> dict:
        """Print and return a summary of the loaded dataset."""
        first = self[0]
        info = {
            'scene': self.poses_data.get('scene', 'unknown'),
            'num_frames': len(self),
            'resolution': f"{first.rgb.shape[1]}x{first.rgb.shape[0]}",
            'intrinsics': first.intrinsics
        }
        print(f"Scene:         {info['scene']}")
        print(f"Frames:        {info['num_frames']}")
        print(f"Resolution:    {info['resolution']}")
        print(f"HFOV:          {first.intrinsics.get('hfov_deg', '?')}°")
        print(f"Focal length:  fx={first.intrinsics.get('fx', '?')}")
        return info


# ── Quick test when run directly ──────────────────────────────
if __name__ == '__main__':
    loader = FrameLoader()
    info = loader.summary()
    print()
    # Inspect a few frames at different positions in the walkthrough
    for i in [0, 5, 10]:
        frame = loader[i]
        print(f"  Frame {i:04d}: {frame.rgb.shape} rgb, {frame.depth.shape} depth, "
              f"camera at ({frame.pose[0,3]:.1f}, {frame.pose[2,3]:.1f})")