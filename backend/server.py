#!/usr/bin/env python3
"""Hyrolic API server — handles IFC file upload and BIM comparison.

A minimal FastAPI/HTTP server that accepts IFC file uploads, parses them,
and returns the BIM JSON. Also serves the frontend static files.

Usage:
    python3 backend/server.py
    # Then open http://localhost:8080
"""

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

# Try to use FastAPI for a proper API, fall back to http.server
try:
    from fastapi import FastAPI, UploadFile, File
    from fastapi.responses import JSONResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# ── Paths ─────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / 'frontend'
DATA_DIR = REPO_ROOT / 'data'
BIM_DIR = DATA_DIR / 'bim'

if HAS_FASTAPI:
    # ── FastAPI server ───────────────────────────────────────
    app = FastAPI(title="Hyrolic API")

    # Serve frontend static files
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

    @app.get("/")
    async def index():
        """Serve the main page (compare.html)."""
        html_path = FRONTEND_DIR / 'compare.html'
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(), status_code=200)
        return JSONResponse({"error": "Frontend not found"}, status_code=404)

    @app.post("/api/upload-ifc")
    async def upload_ifc(file: UploadFile = File(...)):
        """Upload an IFC file, parse it, and return the BIM JSON.

        Accepts .ifc files, runs the IFC parser, saves the result
        to data/bim/, and returns the parsed JSON.
        """
        if not file.filename or not file.filename.lower().endswith('.ifc'):
            return JSONResponse(
                {"error": "Only .ifc files are accepted"},
                status_code=400
            )

        # Save uploaded file temporarily
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_path = tmp_dir / file.filename
        try:
            content = await file.read()
            tmp_path.write_bytes(content)

            # Parse the IFC file
            from backend.bim_compare.ifc_parser import parse_ifc
            result = parse_ifc(tmp_path)

            # Save to data/bim/ with a unique name
            out_name = f"{Path(file.filename).stem}_{uuid.uuid4().hex[:8]}.json"
            out_path = BIM_DIR / out_name
            BIM_DIR.mkdir(parents=True, exist_ok=True)
            with open(out_path, 'w') as f:
                json.dump(result, f, indent=2)

            return JSONResponse({
                "status": "ok",
                "filename": out_name,
                "path": str(out_path),
                "project": result.get('project', 'Unknown'),
                "num_objects": result.get('num_objects', 0),
                "objects": result.get('objects', []),
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        finally:
            # Clean up temp file
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @app.get("/api/bim-files")
    async def list_bim_files():
        """List all available BIM JSON files in data/bim/."""
        files = []
        if BIM_DIR.exists():
            for f in sorted(BIM_DIR.glob("*.json")):
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                })
        return JSONResponse({"files": files})

    @app.get("/api/bim/{filename}")
    async def get_bim_file(filename: str):
        """Get a specific BIM JSON file by name."""
        file_path = BIM_DIR / filename
        if not file_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)
        data = json.loads(file_path.read_text())
        return JSONResponse(data)

else:
    # ── Fallback: simple HTTP server ─────────────────────────
    # This provides basic file serving but not the upload API.
    # Install FastAPI for full functionality: pip install fastapi uvicorn
    print("FastAPI not installed. Install with: pip install fastapi uvicorn", file=sys.stderr)
    print("Falling back to basic file server (no upload API)...", file=sys.stderr)

    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

        def log_message(self, format, *args):
            print(f"[Hyrolic] {args[0]} {args[1]} {args[2]}")

    PORT = 8080
    print(f"Serving frontend at http://localhost:{PORT}")
    print("Upload API requires FastAPI. Install: pip install fastapi uvicorn")
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == '__main__':
    if HAS_FASTAPI:
        print(f"Hyrolic API server starting at http://localhost:8080")
        print(f"Upload IFC files to http://localhost:8080/api/upload-ifc")
        uvicorn.run(app, host="0.0.0.0", port=8080)
