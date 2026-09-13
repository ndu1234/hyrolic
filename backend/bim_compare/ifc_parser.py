#!/usr/bin/env python3
"""IFC parser — converts IFC BIM models into Hyrolic's BIM JSON format.

Takes an IFC file (exported from Revit, ArchiCAD, etc.) and extracts
objects with their positions, dimensions, types, and properties.

Output format matches test-site-01-bim.json:
  {
    "project": "Project Name",
    "source": "ifc",
    "schema": "hyrolic-bim-v1",
    "objects": [
      {
        "id": "col-01",
        "name": "Column A1",
        "ifc_type": "IfcColumn",
        "category": "structural",
        "position": {"x": 3.0, "y": 0.0, "z": -2.0},
        "dimensions": {"width": 0.6, "depth": 0.6, "height": 4.0},
        "material": "concrete"
      },
      ...
    ]
  }

Usage:
    python3 backend/bim_compare/ifc_parser.py path/to/model.ifc
    python3 backend/bim_compare/ifc_parser.py path/to/model.ifc --output data/bim/my-model.json
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

try:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.placement
    import ifcopenshell.util.element
except ImportError:
    print("ifcopenshell not installed. Run: pip install ifcopenshell", file=sys.stderr)
    sys.exit(1)

# ── Map IFC types to Hyrolic categories ──────────────────────
IFC_CATEGORY_MAP = {
    'IfcColumn': 'structural',
    'IfcSlab': 'structural',
    'IfcBeam': 'structural',
    'IfcFooting': 'structural',
    'IfcPile': 'structural',
    'IfcWall': 'architectural',
    'IfcWallStandardCase': 'architectural',
    'IfcDoor': 'architectural',
    'IfcWindow': 'architectural',
    'IfcRoof': 'architectural',
    'IfcStair': 'architectural',
    'IfcReinforcingBar': 'reinforcement',
    'IfcReinforcingMesh': 'reinforcement',
    'IfcTendon': 'reinforcement',
    'IfcPipeSegment': 'mechanical',
    'IfcPipeFitting': 'mechanical',
    'IfcDuctSegment': 'mechanical',
    'IfcDuctFitting': 'mechanical',
    'IfcFlowSegment': 'mechanical',
    'IfcFlowFitting': 'mechanical',
    'IfcFlowController': 'mechanical',
    'IfcFlowTerminal': 'mechanical',
    'IfcFlowTreatmentDevice': 'mechanical',
    'IfcFlowMovingDevice': 'mechanical',
    'IfcElectricDistributionPoint': 'mechanical',
    'IfcElectricAppliance': 'mechanical',
    'IfcElectricFlowStorageDevice': 'mechanical',
    'IfcCableCarrierFitting': 'mechanical',
    'IfcCableCarrierSegment': 'mechanical',
    'IfcCableSegment': 'mechanical',
    'IfcLightFixture': 'mechanical',
    'IfcSwitchingDevice': 'mechanical',
    'IfcSensor': 'mechanical',
    'IfcAlarm': 'mechanical',
    'IfcOutlet': 'mechanical',
    'IfcJunctionBox': 'mechanical',
    'IfcEnergyConversionDevice': 'mechanical',
    'IfcEngine': 'mechanical',
    'IfcEvaporativeCooler': 'mechanical',
    'IfcSpaceHeater': 'mechanical',
    'IfcTubeBundle': 'mechanical',
    'IfcUnitaryEquipment': 'mechanical',
    'IfcValve': 'mechanical',
    'IfcCoil': 'mechanical',
    'IfcChiller': 'mechanical',
    'IfcBoiler': 'mechanical',
    'IfcBurner': 'mechanical',
    'IfcCondenser': 'mechanical',
    'IfcCompressor': 'mechanical',
    'IfcCoolingTower': 'mechanical',
    'IfcDamper': 'mechanical',
    'IfcFan': 'mechanical',
    'IfcFilter': 'mechanical',
    'IfcHeatExchanger': 'mechanical',
    'IfcHumidifier': 'mechanical',
    'IfcMotorConnection': 'mechanical',
    'IfcPump': 'mechanical',
    'IfcTank': 'mechanical',
}

# Types we skip (not useful for BIM comparison)
SKIP_TYPES = {
    'IfcBuilding', 'IfcBuildingStorey', 'IfcSite', 'IfcProject',
    'IfcPresentationLayerAssignment', 'IfcCartesianPoint',
    'IfcDirection', 'IfcAxis2Placement3D', 'IfcLocalPlacement',
    'IfcOwnerHistory', 'IfcApplication', 'IfcPersonAndOrganization',
    'IfcPropertySet', 'IfcPropertySingleValue',
    'IfcRelDefinesByProperties', 'IfcRelAggregates',
    'IfcRelContainedInSpatialStructure', 'IfcRelVoidsElement',
    'IfcOpeningElement', 'IfcSpace', 'IfcSurfaceCurveSweptAreaSolid',
    'IfcExtrudedAreaSolid', 'IfcRectangleProfileDef',
}


def get_ifc_type_name(entity) -> str:
    """Get the IFC type name from an entity, handling wrapped types."""
    return entity.is_a() if hasattr(entity, 'is_a') else str(type(entity).__name__)


def get_object_placement(entity) -> np.ndarray:
    """Extract the 4x4 placement matrix for an IFC entity.

    Uses ifcopenshell's utility to compute the absolute placement
    (including parent hierarchy) in world coordinates.
    """
    try:
        # Get the placement relative to the object's local coordinate system
        placement = ifcopenshell.util.placement.get_local_placement(entity.ObjectPlacement)
        if placement is not None:
            return placement
    except Exception:
        pass
    return np.eye(4)


def get_object_dimensions(entity) -> dict:
    """Extract bounding box dimensions from an IFC entity.

    Uses the geometry representation to compute the approximate size.
    Falls back to property sets if geometry is not available.
    """
    # Try to get dimensions from property sets first
    try:
        props = ifcopenshell.util.element.get_psets(entity)
        for pset_name, pset in props.items():
            if isinstance(pset, dict):
                dims = {}
                for key in ['Width', 'Length', 'Height', 'Depth', 'Diameter', 'Thickness']:
                    if key in pset:
                        val = pset[key]
                        if isinstance(val, (int, float)):
                            dims[key.lower()] = float(val)
                if dims:
                    return dims
    except Exception:
        pass

    # Fallback: try to get bounding box from geometry
    try:
        settings = ifcopenshell.geom.settings()
        shape = ifcopenshell.geom.create_shape(settings, entity)
        if shape:
            verts = shape.geometry.verts
            if verts and len(verts) >= 3:
                # Reshape to (N, 3) and find min/max
                pts = np.array(verts).reshape(-1, 3)
                mins = pts.min(axis=0)
                maxs = pts.max(axis=0)
                return {
                    'width': float(maxs[0] - mins[0]),
                    'height': float(maxs[1] - mins[1]),
                    'depth': float(maxs[2] - mins[2]),
                }
    except Exception:
        pass

    return {}


def get_material_name(entity) -> str:
    """Extract the primary material name from an IFC entity."""
    try:
        # Check for material association
        for rel in entity.HasAssociations or []:
            if rel.is_a('IfcRelAssociatesMaterial'):
                material = rel.RelatingMaterial
                if material.is_a('IfcMaterial'):
                    return material.Name
                elif material.is_a('IfcMaterialLayerSetUsage'):
                    return material.ForLayerSet.MaterialSet.Name
    except Exception:
        pass
    return 'unknown'


def parse_ifc(ifc_path: Path) -> dict:
    """Parse an IFC file and convert to Hyrolic BIM JSON format.

    Args:
        ifc_path: Path to the .ifc file

    Returns:
        Dict matching the BIM JSON schema
    """
    print(f"Loading IFC file: {ifc_path}")
    ifc_file = ifcopenshell.open(str(ifc_path))

    # Get project name
    project_name = 'Unknown Project'
    for project in ifc_file.by_type('IfcProject'):
        project_name = project.Name or project_name
        break

    objects = []
    skipped = 0

    # Iterate over all spatial structure elements and their contained elements
    # This gives us the actual building elements (walls, columns, slabs, etc.)
    for element in ifc_file.by_type('IfcProduct'):
        type_name = get_ifc_type_name(element)

        # Skip non-physical types
        if type_name in SKIP_TYPES:
            skipped += 1
            continue

        # Skip if no name (usually means it's a helper geometry)
        name = getattr(element, 'Name', None) or getattr(element, 'name', None)
        if not name:
            skipped += 1
            continue

        # Get category from type map
        category = IFC_CATEGORY_MAP.get(type_name, 'other')

        # Get placement matrix
        placement = get_object_placement(element)
        position = {
            'x': round(float(placement[0, 3]), 3),
            'y': round(float(placement[1, 3]), 3),
            'z': round(float(placement[2, 3]), 3),
        }

        # Get dimensions
        dims = get_object_dimensions(element)
        dimensions = {}
        for k, v in dims.items():
            dimensions[k] = round(float(v), 3)

        # Get material
        material = get_material_name(element)

        # Generate a stable ID from the element's unique ID
        element_id = str(element.id() if hasattr(element, 'id') else element.GlobalId)

        obj = {
            'id': element_id,
            'name': str(name),
            'ifc_type': type_name,
            'category': category,
            'position': position,
            'dimensions': dimensions,
            'material': material,
        }
        objects.append(obj)

    # Build output
    result = {
        'project': project_name,
        'source': 'ifc',
        'schema': 'hyrolic-bim-v1',
        'num_objects': len(objects),
        'objects': objects,
    }

    print(f"  Project: {project_name}")
    print(f"  Objects extracted: {len(objects)}")
    print(f"  Skipped (non-physical): {skipped}")

    # Show category breakdown
    from collections import Counter
    cats = Counter(obj['category'] for obj in objects)
    for cat, count in cats.most_common():
        print(f"    {cat}: {count}")

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('ifc_path', type=str, help='Path to .ifc file')
    ap.add_argument('--output', '-o', type=str, default=None,
                    help='Output JSON path (default: data/bim/<filename>.json)')
    args = ap.parse_args()

    ifc_path = Path(args.ifc_path)
    if not ifc_path.exists():
        print(f"File not found: {ifc_path}", file=sys.stderr)
        sys.exit(1)

    result = parse_ifc(ifc_path)

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = Path(__file__).resolve().parents[2] / 'data' / 'bim' / f'{ifc_path.stem}.json'

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\nWrote {out_path}")
    print(f"Run comparison: python3 backend/bim_compare/compare.py --bim {out_path}")


if __name__ == '__main__':
    main()
