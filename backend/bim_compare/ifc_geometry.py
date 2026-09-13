#!/usr/bin/env python3
"""IFC geometry extractor — tessellates IFC elements into a web-viewable GLB.

Converts an IFC file into:
  1. A GLB (glTF binary) containing real 3D geometry for every element,
     with each element as a node named by its element index — the "geometry cache".
  2. A manifest.json mapping each element to its metadata (ID, name, type,
     GUID, category, psets, storey) — the "element data".
  3. An optional SQLite database with the same element data.

This feeds the 3D viewer (Three.js + GLTFLoader) so users can select,
hide, and section the model.

Usage:
    python3 backend/bim_compare/ifc_geometry.py /path/to/model.ifc --out data/bim/model_name
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

try:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element
    import ifcopenshell.util.placement
    import trimesh
except ImportError:
    print("Missing deps. Install: pip install ifcopenshell trimesh", file=sys.stderr)
    sys.exit(1)

# ── Category map (same as ifc_parser.py) ─────────────────────
IFC_CATEGORY_MAP = {
    'IfcColumn': 'structural', 'IfcSlab': 'structural', 'IfcBeam': 'structural',
    'IfcFooting': 'structural', 'IfcPile': 'structural',
    'IfcWall': 'architectural', 'IfcWallStandardCase': 'architectural',
    'IfcDoor': 'architectural', 'IfcWindow': 'architectural',
    'IfcRoof': 'architectural', 'IfcStair': 'architectural',
    'IfcReinforcingBar': 'reinforcement', 'IfcReinforcingMesh': 'reinforcement',
    'IfcTendon': 'reinforcement',
    'IfcPipeSegment': 'mechanical', 'IfcPipeFitting': 'mechanical',
    'IfcDuctSegment': 'mechanical', 'IfcDuctFitting': 'mechanical',
    'IfcFlowSegment': 'mechanical', 'IfcFlowFitting': 'mechanical',
    'IfcFlowController': 'mechanical', 'IfcFlowTerminal': 'mechanical',
    'IfcFlowTreatmentDevice': 'mechanical', 'IfcFlowMovingDevice': 'mechanical',
    'IfcElectricDistributionPoint': 'mechanical', 'IfcElectricAppliance': 'mechanical',
    'IfcElectricFlowStorageDevice': 'mechanical',
    'IfcCableCarrierFitting': 'mechanical', 'IfcCableCarrierSegment': 'mechanical',
    'IfcCableSegment': 'mechanical', 'IfcLightFixture': 'mechanical',
    'IfcSwitchingDevice': 'mechanical', 'IfcSensor': 'mechanical',
    'IfcAlarm': 'mechanical', 'IfcOutlet': 'mechanical', 'IfcJunctionBox': 'mechanical',
    'IfcEnergyConversionDevice': 'mechanical', 'IfcEngine': 'mechanical',
    'IfcEvaporativeCooler': 'mechanical', 'IfcSpaceHeater': 'mechanical',
    'IfcTubeBundle': 'mechanical', 'IfcUnitaryEquipment': 'mechanical',
    'IfcValve': 'mechanical', 'IfcCoil': 'mechanical', 'IfcChiller': 'mechanical',
    'IfcBoiler': 'mechanical', 'IfcBurner': 'mechanical', 'IfcCondenser': 'mechanical',
    'IfcCompressor': 'mechanical', 'IfcCoolingTower': 'mechanical',
    'IfcDamper': 'mechanical', 'IfcFan': 'mechanical', 'IfcFilter': 'mechanical',
    'IfcHeatExchanger': 'mechanical', 'IfcHumidifier': 'mechanical',
    'IfcMotorConnection': 'mechanical', 'IfcPump': 'mechanical', 'IfcTank': 'mechanical',
}

SKIP_TYPES = {
    'IfcBuilding', 'IfcBuildingStorey', 'IfcSite', 'IfcProject',
    'IfcPresentationLayerAssignment', 'IfcCartesianPoint', 'IfcDirection',
    'IfcAxis2Placement3D', 'IfcLocalPlacement', 'IfcOwnerHistory',
    'IfcApplication', 'IfcPersonAndOrganization', 'IfcPropertySet',
    'IfcPropertySingleValue', 'IfcRelDefinesByProperties', 'IfcRelAggregates',
    'IfcRelContainedInSpatialStructure', 'IfcRelVoidsElement',
    'IfcOpeningElement', 'IfcSpace', 'IfcSurfaceCurveSweptAreaSolid',
    'IfcExtrudedAreaSolid', 'IfcRectangleProfileDef',
}


def get_storey_name(element) -> str:
    """Find which building storey an element belongs to."""
    try:
        # Traverse the containment relationship
        for rel in ifcopenshell.util.element.get_aggregate_type_container(
                element, 'IfcBuildingStorey') or []:
            if rel.is_a('IfcBuildingStorey'):
                return rel.Name or 'Unknown'
    except Exception:
        pass
    # Fallback: check spatial containment directly
    try:
        for rel in element.ContainedInStructure or []:
            if rel.RelatingStructure.is_a('IfcBuildingStorey'):
                return rel.RelatingStructure.Name or 'Unknown'
    except Exception:
        pass
    return None


def get_psets(element) -> dict:
    """Extract property sets for an element (flattened to JSON-safe dicts)."""
    psets = {}
    try:
        raw = ifcopenshell.util.element.get_psets(element)
        for pset_name, props in raw.items():
            if isinstance(props, dict):
                cleaned = {}
                for k, v in props.items():
                    # Convert IFC quantity/length types to plain values
                    if hasattr(v, 'is_a'):
                        v = getattr(v, 'val', None) or str(v)
                    if isinstance(v, (int, float, str, bool)) or v is None:
                        cleaned[k] = v
                    else:
                        cleaned[k] = str(v)[:200]
                psets[pset_name] = cleaned
    except Exception:
        pass
    return psets


def tessellate_element(element):  # returns trimesh.Trimesh | None (py3.9 compat)
    """Tessellate an IFC element into vertices + triangles.

    Returns a trimesh.Trimesh in METERS (IFC is millimeters).
    Returns None if the element has no geometry.
    """
    try:
        settings = ifcopenshell.geom.settings()
        # No triangulation simplification — keep full detail
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        if shape is None:
            return None

        verts = np.asarray(shape.geometry.verts, dtype=np.float64).reshape(-1, 3) / 1000.0
        # ifcopenshell indices are flat quadruples (0,1,2, 0,2,3) in newer versions,
        # or triangles in older. Detect by face count consistency.
        faces_flat = np.asarray(shape.geometry.faces, dtype=np.int64)
        if len(faces_flat) % 3 == 0:
            faces = faces_flat.reshape(-1, 3)
        else:
            faces = faces_flat.reshape(-1, 4)[:, [0, 1, 2]]  # quads -> triangles

        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        # Remove degenerate faces (zero-area triangles)
        if hasattr(mesh, 'remove_degenerate_faces'):
            mesh.remove_degenerate_faces()
        else:
            # Same result: keep faces whose area > 0
            areas = mesh.area_faces
            keep = np.where(areas > 1e-12)[0]
            if len(keep) < len(mesh.faces):
                mesh.update_faces(keep)
        if len(mesh.faces) == 0:
            return None
        return mesh
    except Exception:
        return None


def extract_ifc(ifc_path: Path, out_dir: Path, use_sqlite: bool = True):
    """Extract geometry + metadata from an IFC file.

    Args:
        ifc_path: Path to the .ifc file
        out_dir: Output directory (geometry.glb, manifest.json, elements.db)
        use_sqlite: Also write a SQLite DB of element metadata
    """
    print(f"Loading IFC: {ifc_path}")
    ifc = ifcopenshell.open(str(ifc_path))

    project_name = 'Unknown Project'
    for p in ifc.by_type('IfcProject'):
        project_name = p.Name or project_name
        break

    # ── Build element list with geometry ──────────────────────
    elements = []       # web scene nodes metadata
    meshes = []         # trimesh objects for GLB export
    node_names = []     # per-mesh node name in the GLB = element index
    stats = {'total': 0, 'with_geometry': 0, 'skipped': 0, 'no_geometry': 0}

    for element in ifc.by_type('IfcProduct'):
        stats['total'] += 1
        type_name = element.is_a()
        if type_name in SKIP_TYPES:
            stats['skipped'] += 1
            continue
        name = getattr(element, 'Name', None) or type_name
        if not name:
            stats['skipped'] += 1
            continue

        # Geometry (millimeters -> meters)
        mesh = tessellate_element(element)
        if mesh is None:
            stats['no_geometry'] += 1
            # Still record the element so 'missing' elements are visible in UI
        else:
            stats['with_geometry'] += 1
            index = len(meshes)
            meshes.append(mesh)
            node_names.append(str(index))

        # Metadata
        guid = getattr(element, 'GlobalId', None) or str(element.id())
        position = np.eye(4)
        try:
            placement = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
            if placement is not None:
                position = np.asarray(placement, dtype=float)
        except Exception:
            pass

        elements.append({
            'index': node_names[-1] if mesh is not None else None,
            'id': str(element.id()),
            'guid': str(guid),
            'name': str(name),
            'ifc_type': type_name,
            'category': IFC_CATEGORY_MAP.get(type_name, 'other'),
            'storey': get_storey_name(element),
            'position_m': {
                'x': round(float(position[0, 3]) / 1000, 3),
                'y': round(float(position[1, 3]) / 1000, 3),
                'z': round(float(position[2, 3]) / 1000, 3),
            },
            'psets': get_psets(element),
        })

    print(f"  scanned: {stats['total']}, with geometry: {stats['with_geometry']}, "
          f"no geometry: {stats['no_geometry']}, skipped: {stats['skipped']}")

    # ── Export GLB (geometry cache) ───────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / 'geometry.glb'
    if meshes:
        scene = trimesh.Scene()
        for i, m in enumerate(meshes):
            scene.add_geometry(m, node_name=node_names[i])
        # Colors by category for nicer default view
        for node_name, m in zip(node_names, meshes):
            pass  # trimesh Scene export keeps per-mesh visuals
        scene.export(str(glb_path))
        print(f"  GLB: {glb_path} ({glb_path.stat().st_size/1e6:.1f} MB)")
    else:
        print("  WARNING: no geometry found — GLB not written")

    # ── Write manifest.json (element data) ────────────────────
    manifest = {
        'project': project_name,
        'source': 'ifc',
        'schema': 'hyrolic-ifc-v1',
        'num_elements': len(elements),
        'num_with_geometry': stats['with_geometry'],
        'units': 'meters',
        'glb': 'geometry.glb',
        'elements': elements,
    }
    manifest_path = out_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=1))
    print(f"  Manifest: {manifest_path}")

    # ── Write SQLite (element data store) ─────────────────────
    if use_sqlite:
        db_path = out_dir / 'elements.db'
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS elements (
                node_index TEXT, id TEXT, guid TEXT, name TEXT,
                ifc_type TEXT, category TEXT, storey TEXT,
                position TEXT, psets TEXT
            )
        """)
        for e in elements:
            conn.execute(
                "INSERT INTO elements VALUES (?,?,?,?,?,?,?,?,?)",
                (e['index'], e['id'], e['guid'], e['name'],
                 e['ifc_type'], e['category'], e['storey'],
                 json.dumps(e['position_m']), json.dumps(e['psets']))
            )
        conn.commit()
        conn.close()
        print(f"  SQLite: {db_path}")

    print(f"\nDone. Load in viewer via manifest.json + geometry.glb")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('ifc_path', type=str, help='Path to .ifc file')
    ap.add_argument('--out', '-o', type=str, default=None,
                    help='Output directory (default: data/bim/<name>/)')
    ap.add_argument('--no-sqlite', action='store_true',
                    help='Skip SQLite export (JSON only)')
    args = ap.parse_args()

    ifc_path = Path(args.ifc_path)
    if not ifc_path.exists():
        print(f"File not found: {ifc_path}", file=sys.stderr)
        sys.exit(1)

    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = Path(__file__).resolve().parents[2] / 'data' / 'bim' / ifc_path.stem

    extract_ifc(ifc_path, out_dir, use_sqlite=not args.no_sqlite)


if __name__ == '__main__':
    main()