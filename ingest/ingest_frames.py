#!/usr/bin/env python3
"""Ingest camera frames: index RGB frames + metadata alongside LiDAR point clouds.

Takes a site folder with frames/ subdirectory and produces a frames manifest
(filenames, timestamps, camera pose references) to pair with the LiDAR manifest.

Usage:
    python3 ingest/ingest_frames.py --site data/sites/<site-name>
"""
# TODO: implement frame indexing — read frame timestamps, extract EXIF,
# match to LiDAR poses, write frames-manifest.json

if __name__ == "__main__":
    print("ingest_frames.py — not yet implemented")
