# backend/jetson/ — Jetson-specific code (placeholder)

When we get the Go2 X + Jetson, these files replace the Mac/synthetic code paths:

## Placeholder files to implement:

- **camera.py** — Live camera capture from Go2 X's RealSense D435i + HD camera.
  On Mac: `backend/ingest/frame_loader.py` loads synthetic frames from disk.
  On Jetson: This reads live frames from the robot's cameras.

- **yolo_trt.py** — YOLO inference via TensorRT (NVIDIA's optimized runtime).
  On Mac: Standard YOLO via PyTorch/ultralytics.
  On Jetson: Compiled to TensorRT engine for 2-3x faster inference.

- **robot_interface.py** — SDK interface to Go2 X (pose, odometry, commands).
  On Mac: Robot pose comes from camera_poses.json (synthetic).
  On Jetson: Reads live odometry from the robot over the internal network.

## How the switch works

```python
from backend.config import is_jetson

if is_jetson():
    from backend.jetson.camera import Go2Camera
    camera = Go2Camera()
else:
    from backend.ingest.frame_loader import FrameLoader
    camera = FrameLoader(scene='test-site-01')
```

Set `HYROLIC_PLATFORM=jetson` to test Jetson code paths on your Mac
(for syntax checks etc. — obviously won't actually connect to hardware).