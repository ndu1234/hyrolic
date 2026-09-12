# detection/ — Computer Vision Pipeline

Go2 X camera frame processing.

## Files

- `detect.py` — YOLOv8 inference on RGB frames. Detects construction elements (columns, walls, rebar, pipes, doors).
- `tracker.py` — Multi-object tracking across frames. Deduplicates detections so "Column A1" seen 47 times becomes one entry.
- `project_3d.py` — Projects 2D bounding boxes into 3D site coordinates using the LiDAR-aligned camera pose from the robot's odometry.

## Input

- RGB frames from `data/sites/<site>/<date>/frames/`
- Camera pose from robot odometry (timestamped per frame)

## Output

- `detected-site-model.json` — list of detected objects with type, 3D position (approx ±10cm), dimensions, confidence, and evidence frames.
