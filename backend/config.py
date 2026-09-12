"""Hyrolic — Platform abstraction layer.

Switches between Mac (development) and Jetson (deployment) modes.
Auto-detects at import time, or can be overridden with env var.

Usage:
    # Auto-detect (recommended)
    from backend import platform
    platform.is_jetson()  # True on Jetson, False on Mac

    # Force a specific mode
    HYROLIC_PLATFORM=jetson python3 backend/detect.py ...

    # Or in code:
    import backend.config as cfg
    cfg.PLATFORM = 'jetson'  # override
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

# ── Platform constants ────────────────────────────────────────
PLATFORM_MAC = 'mac'
PLATFORM_JETSON = 'jetson'
PLATFORM_UNKNOWN = 'unknown'

# ── Public state (can be overridden at runtime) ────────────────
# Default: auto-detect. Set HYROLIC_PLATFORM=jetson to force Jetson mode.
PLATFORM = os.environ.get('HYROLIC_PLATFORM', 'auto')


def detect() -> str:
    """Detect the current hardware platform.

    Returns:
        'jetson' if running on an NVIDIA Jetson (ARM64 + NVIDIA GPU)
        'mac' if running on macOS
        'unknown' if we can't determine
    """
    # If explicitly set via env var, respect that
    if PLATFORM != 'auto':
        return PLATFORM

    # macOS detection
    if sys.platform == 'darwin':
        return PLATFORM_MAC

    # Jetson detection: Linux + ARM64 + NVIDIA GPU
    if sys.platform == 'linux':
        # Check if we're on an ARM architecture
        machine = platform.machine()
        if machine in ('aarch64', 'arm64'):
            # Check for NVIDIA Jetson by looking for tegra or jetson in device tree
            try:
                dt_model = Path('/proc/device-tree/model').read_text().strip().lower()
                if 'jetson' in dt_model or 'tegra' in dt_model:
                    return PLATFORM_JETSON
            except (FileNotFoundError, OSError):
                pass

            # Also check for NVIDIA GPU via lspci or nvidia-smi
            try:
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and 'nvidia' in result.stdout.lower():
                    return PLATFORM_JETSON
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            # Check for Tegra device
            try:
                result = subprocess.run(
                    ['uname', '-a'], capture_output=True, text=True, timeout=5
                )
                if 'tegra' in result.stdout.lower() or 'jetson' in result.stdout.lower():
                    return PLATFORM_JETSON
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    return PLATFORM_UNKNOWN


def is_jetson() -> bool:
    """Returns True if running on an NVIDIA Jetson."""
    return detect() == PLATFORM_JETSON


def is_mac() -> bool:
    """Returns True if running on macOS."""
    return detect() == PLATFORM_MAC


def require_jetson(feature_name: str = "this feature"):
    """Call at the top of Jetson-only functions to fail gracefully on Mac."""
    if not is_jetson():
        raise NotImplementedError(
            f"{feature_name} requires an NVIDIA Jetson. "
            f"Currently running on {detect().upper()}.\n"
            f"  Set HYROLIC_PLATFORM=jetson to test Jetson code paths on Mac."
        )


# ── Platform-specific paths ────────────────────────────────────
def repo_root() -> Path:
    """Absolute path to the repo root (works on both Mac and Jetson)."""
    # __file__ is backend/config.py, so parents[1] = repo root
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """Data directory. Same on both platforms."""
    return repo_root() / 'data'


def synthetic_dir() -> Path:
    """Synthetic test data directory."""
    return data_dir() / 'synthetic'


def sites_dir() -> Path:
    """Site capture data directory."""
    return data_dir() / 'sites'


def camera_poses_path(scene_name: str = 'test-site-01') -> Path:
    """Path to camera_poses.json for a given scene."""
    return synthetic_dir() / scene_name / 'camera_poses.json'


def render_dir(scene_name: str = 'test-site-01') -> Path:
    """Path to rendered frames for a given scene."""
    return synthetic_dir() / scene_name / 'renders'


# ── Platform-specific imports (lazy) ───────────────────────────
# On Jetson, some imports differ (e.g., TensorRT vs PyTorch, or
# different Open3D version). These helpers load the right thing.

def import_yolo():
    """Import YOLO — PyTorch on Mac, TensorRT on Jetson."""
    if is_jetson():
        # Placeholder: Jetson will use TensorRT-optimized YOLO
        # from backend.jetson.yolo_trt import YOLO_TRT
        # return YOLO_TRT(...)
        require_jetson("YOLO TensorRT backend — not yet implemented")
    else:
        # Mac/isual development: use ultralytics YOLO
        try:
            from ultralytics import YOLO
            return YOLO
        except ImportError:
            print("Install ultralytics: pip install ultralytics", file=sys.stderr)
            raise


def import_camera():
    """Import camera interface — synthetic on Mac, live on Jetson."""
    if is_jetson():
        # Placeholder: Jetson will read from Go2 X's RealSense/camera
        # from backend.jetson.camera import Go2Camera
        # return Go2Camera(...)
        require_jetson("Go2 X live camera — not yet implemented")
    else:
        # Mac: load frames from synthetic renders
        from backend.ingest.frame_loader import FrameLoader
        return FrameLoader


# ── Device info ────────────────────────────────────────────────
def device_info() -> dict:
    """Return a dict with platform and hardware info."""
    info = {
        'platform': detect(),
        'machine': platform.machine(),
        'system': platform.system(),
        'python': sys.version,
    }

    if is_jetson():
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(', ')
                info['gpu'] = parts[0] if len(parts) > 0 else 'unknown'
                info['gpu_memory'] = parts[1] if len(parts) > 1 else 'unknown'
        except Exception:
            info['gpu'] = 'NVIDIA (detected)'

    return info


# ── Print banner on import ─────────────────────────────────────
if __name__ != '__main__':
    _detected = detect()
    if _detected == PLATFORM_JETSON:
        print(f"[Hyrolic] Running on JETSON — edge deployment mode")
    elif _detected == PLATFORM_MAC:
        pass  # Silent on Mac, no need to announce
    else:
        print(f"[Hyrolic] Running on {_detected.upper()} — limited functionality")


# ── CLI entry point ────────────────────────────────────────────
if __name__ == '__main__':
    import json
    info = device_info()
    print(f"Platform: {info['platform']}")
    print(f"Machine:  {info['machine']}")
    print(f"System:   {info['system']}")
    print(f"Python:   {info['python']}")
    if 'gpu' in info:
        print(f"GPU:      {info['gpu']}")
        print(f"Memory:   {info['gpu_memory']}")

    print()
    if is_jetson():
        print("✓ Jetson mode active — all hardware features available")
    elif is_mac():
        print("✓ Mac mode active — using synthetic data and CPU inference")
        print("  Set HYROLIC_PLATFORM=jetson to test Jetson code paths")