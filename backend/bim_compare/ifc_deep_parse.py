#!/usr/bin/env python3
"""Full IFC parser — extracts every element, property, relation, material, quantity.

Navisworks-style: parses IFC files down to the finest detail, preserving the
full spatial hierarchy (project → site → building → storey → element) with
all properties (Psets, BaseQuantities), materials, relations, and classifications.

Output: A single JSON file with the complete building data model, or a SQLite
database for the comparison engine to query.

Usage:
    python3 backend/bim_compare/ifc_deep_parse.py path/to/model.ifc --out data/bim/model_name
    python3 backend/bim_compare/ifc_deep_parse.py path/to/model.ifc --out data/bim/model_name --sqlite
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    import ifcopenshell
    import ifcopenshell.util.element
    import ifcopenshell.util.placement
except ImportError:
    print("ifcopenshell required. Install: pip install ifcopenshell", file=sys.stderr)
    sys.exit(1)


# ── Helper: safe attribute access ────────────────────────────
def safe(val, default="—"):
    """Return a JSON-safe value from an IFC attribute."""
    if val is None:
        return default
    if isinstance(val, (int, float, str, bool)):
        return val
    if hasattr(val, 'is_a'):
        # IFC entity reference
        return str(val.id())
    if hasattr(val, 'val'):
        return safe(val.val)
    if isinstance(val, tuple):
        return tuple(safe(v) for v in val)
    return str(val)[:500]


def get_entity_name(entity) -> str:
    """Get the Name attribute from an IFC entity safely."""
    try:
        return entity.Name or str(entity.id())
    except (AttributeError, TypeError):
        return str(entity.id())


# ── Parse full IFC data ──────────────────────────────────────
def parse_ifc_deep(ifc_path: Path) -> dict:
    """Parse an IFC file into a complete data model.

    Returns a dict with:
      project, sites[], buildings[], storeys[], elements[],
      materials[], classifications[], element_map (guid -> element)
    """
    print(f"Loading IFC: {ifc_path.name} ({ifc_path.stat().st_size / 1e6:.0f} MB)")
    ifc = ifcopenshell.open(str(ifc_path))

    # ── Project metadata ──────────────────────────────────────
    project = None
    for p in ifc.by_type('IfcProject'):
        project = {
            'id': p.id(),
            'name': p.Name or 'Unnamed Project',
            'long_name': getattr(p, 'LongName', None),
            'description': getattr(p, 'Description', None),
            'phase': getattr(p, 'Phase', None),
        }
        break

    # ── Spatial structure: Sites → Buildings → Storeys ────────
    sites = []
    buildings = []
    storeys = []
    element_containment = {}  # element_id -> storey_id

    def collect_spatial_structure(parent_entity, parent_list, level=0):
        """Recursively collect spatial structure elements."""
        for rel in getattr(parent_entity, 'IsDecomposedBy', []) or []:
            for child in rel.RelatedObjects or []:
                if child.is_a('IfcSite'):
                    site_info = {
                        'id': child.id(),
                        'name': child.Name or 'Unnamed Site',
                        'guid': getattr(child, 'GlobalId', ''),
                        'ref_longitude': getattr(child, 'RefLongitude', None),
                        'ref_latitude': getattr(child, 'RefLatitude', None),
                        'children': [],
                    }
                    sites.append(site_info)
                    collect_spatial_structure(child, site_info['children'], level + 1)
                elif child.is_a('IfcBuilding'):
                    bldg_info = {
                        'id': child.id(),
                        'name': child.Name or 'Unnamed Building',
                        'guid': getattr(child, 'GlobalId', ''),
                        'elevation_of_ref_height': getattr(child, 'ElevationOfRefHeight', None),
                        'children': [],
                    }
                    buildings.append(bldg_info)
                    collect_spatial_structure(child, bldg_info['children'], level + 1)
                elif child.is_a('IfcBuildingStorey'):
                    story_info = {
                        'id': child.id(),
                        'name': child.Name or 'Unnamed Storey',
                        'guid': getattr(child, 'GlobalId', ''),
                        'elevation': getattr(child, 'Elevation', None) or 0.0,
                        'elements': [],
                    }
                    storeys.append(story_info)
                    # Collect elements contained in this storey
                    for rel2 in getattr(child, 'ContainsElements', []) or []:
                        for elem in rel2.RelatedElements or []:
                            element_containment[elem.id()] = story_info['name']

    for p in ifc.by_type('IfcProject'):
        collect_spatial_structure(p, sites)

    # ── All physical elements (products) ──────────────────────
    elements = []
    materials_index = defaultdict(list)  # material_name -> [element_id]
    classification_index = defaultdict(list)  # system -> [element_id]

    skip_types = {
        'IfcBuilding', 'IfcBuildingStorey', 'IfcSite', 'IfcProject',
        'IfcPresentationLayerAssignment', 'IfcCartesianPoint', 'IfcDirection',
        'IfcAxis2Placement3D', 'IfcLocalPlacement', 'IfcOwnerHistory',
        'IfcApplication', 'IfcPersonAndOrganization',
        'IfcRelDefinesByProperties', 'IfcRelAggregates',
        'IfcRelContainedInSpatialStructure', 'IfcRelVoidsElement',
        'IfcOpeningElement', 'IfcSpace', 'IfcSurfaceCurveSweptAreaSolid',
        'IfcExtrudedAreaSolid', 'IfcRectangleProfileDef',
        'IfcRelAssociatesMaterial', 'IfcRelFillsElement',
        'IfcRelConnectsElements', 'IfcRelReferencedInSpatialStructure',
    }

    processed = 0
    skipped = 0
    no_name = 0

    for element in ifc.by_type('IfcProduct'):
        type_name = element.is_a()
        if type_name in skip_types:
            skipped += 1
            continue
        name = getattr(element, 'Name', None) or type_name
        if not name and type_name in ('IfcOpeningElement',):
            skipped += 1
            continue

        processed += 1

        # ── Position ──────────────────────────────────────────
        pos = {'x': 0, 'y': 0, 'z': 0}
        try:
            placement = ifcopenshell.util.placement.get_local_placement(
                element.ObjectPlacement)
            if placement is not None:
                pos = {
                    'x': round(float(placement[0, 3]) / 1000, 3),
                    'y': round(float(placement[1, 3]) / 1000, 3),
                    'z': round(float(placement[2, 3]) / 1000, 3),
                }
        except Exception:
            pass

        # ── Dimensions from geometry (bounding box) ──────────
        dims = {}
        try:
            props = ifcopenshell.util.element.get_psets(element)
            for pset_name, pset in props.items():
                if isinstance(pset, dict):
                    for key in ['Width', 'Length', 'Height', 'Depth',
                                'Diameter', 'Thickness', 'Perimeter']:
                        if key in pset and isinstance(pset[key], (int, float)):
                            dims[key.lower()] = round(float(pset[key]) / 1000, 3)
        except Exception:
            pass

        # ── Materials ─────────────────────────────────────────
        materials = []
        try:
            for rel in element.HasAssociations or []:
                if rel.is_a('IfcRelAssociatesMaterial'):
                    mat = rel.RelatingMaterial
                    if mat.is_a('IfcMaterial'):
                        mat_name = mat.Name or 'Unknown'
                        materials.append(mat_name)
                        materials_index[mat_name].append(element.id())
                    elif mat.is_a('IfcMaterialLayerSetUsage'):
                        for layer in mat.ForLayerSet.MaterialLayers or []:
                            mat_name = layer.Material.Name or 'Unknown'
                            materials.append(mat_name)
                            materials_index[mat_name].append(element.id())
                    elif mat.is_a('IfcMaterialConstituentSet'):
                        for const in mat.MaterialConstituents or []:
                            mat_name = const.Material.Name or 'Unknown'
                            materials.append(mat_name)
                            materials_index[mat_name].append(element.id())
        except Exception:
            pass

        # ── Property Sets ─────────────────────────────────────
        psets = {}
        try:
            raw = ifcopenshell.util.element.get_psets(element)
            for pset_name, props in raw.items():
                if isinstance(props, dict):
                    cleaned = {}
                    for k, v in props.items():
                        if hasattr(v, 'is_a'):
                            v = getattr(v, 'val', None) or str(v)
                        if isinstance(v, (int, float, str, bool)) or v is None:
                            cleaned[k] = v
                        else:
                            cleaned[k] = str(v)[:200]
                    psets[pset_name] = cleaned
        except Exception:
            pass

        # ── Classification ────────────────────────────────────
        classifications = []
        try:
            for rel in element.HasAssociations or []:
                if rel.is_a('IfcRelAssociatesClassification'):
                    cls = rel.RelatingClassification
                    if cls.is_a('IfcClassificationReference'):
                        classifications.append({
                            'system': getattr(cls, 'Identification', ''),
                            'code': getattr(cls, 'Name', ''),
                        })
                        classification_index[cls.Identification].append(element.id())
        except Exception:
            pass

        # ── Element record ────────────────────────────────────
        elem = {
            'id': element.id(),
            'guid': getattr(element, 'GlobalId', None) or str(element.id()),
            'name': str(name),
            'ifc_type': type_name,
            'description': getattr(element, 'Description', None),
            'tag': getattr(element, 'Tag', None),
            'containment': {
                'storey': element_containment.get(element.id()),
                'building': None,
                'site': None,
            },
            'position_m': pos,
            'dimensions': dims,
            'materials': materials,
            'properties': psets,
            'classifications': classifications,
            'has_geometry': False,  # populated later
            'children': [],
            'opening_elements': [],
        }
        elements.append(elem)

    # ── Openings (IfcOpeningElement) related to elements ──────
    # Process IfcRelVoidsElement: element -> opening
    for rel in ifc.by_type('IfcRelVoidsElement'):
        try:
            relating = rel.RelatingBuildingElement
            related = rel.RelatedOpeningElement
            elem_id = relating.id()
            opening_id = related.id()
            # Find the element and add the opening reference
            for e in elements:
                if e['id'] == elem_id:
                    e['opening_elements'].append(opening_id)
                    break
        except Exception:
            pass

    # ── Assign geometry flag ──────────────────────────────────
    for element in ifc.by_type('IfcProduct'):
        eid = element.id()
        try:
            rep = getattr(element, 'Representation', None)
            if rep is not None:
                for e in elements:
                    if e['id'] == eid:
                        e['has_geometry'] = True
                        break
        except Exception:
            pass

    # ── Materials table ───────────────────────────────────────
    materials_list = [
        {'name': name, 'element_ids': ids}
        for name, ids in materials_index.items()
    ]

    # ── Classification table ──────────────────────────────────
    classifications_list = [
        {'system': sys_name, 'element_ids': ids}
        for sys_name, ids in classification_index.items()
    ]

    # ── Assemble output ───────────────────────────────────────
    result = {
        'project': project or {'name': 'Unknown'},
        'schema': 'hyrolic-ifc-deep-v1',
        'statistics': {
            'total_elements': len(elements),
            'total_materials': len(materials_list),
            'total_classifications': len(classifications_list),
            'sites': len(sites),
            'buildings': len(buildings),
            'storeys': len(storeys),
        },
        'spatial_hierarchy': {
            'sites': sites,
            'buildings': buildings,
            'storeys': storeys,
        },
        'elements': elements,
        'materials': materials_list,
        'classifications': classifications_list,
    }

    # Stats
    from collections import Counter
    type_counts = Counter(e['ifc_type'] for e in elements)
    print(f"  Elements extracted: {len(elements)}")
    print(f"  Materials: {len(materials_list)}")
    print(f"  Classifications: {len(classifications_list)}")
    print(f"  Spatial: {len(sites)} sites, {len(buildings)} buildings, {len(storeys)} storeys")
    print(f"\n  Top types:")
    for t, c in type_counts.most_common(10):
        print(f"    {t:35s} x{c}")

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('ifc_path', type=str, help='Path to .ifc file')
    ap.add_argument('--out', '-o', type=str, default=None,
                    help='Output directory (default: data/bim/<name>_deep/)')
    ap.add_argument('--sqlite', action='store_true',
                    help='Also export to SQLite')
    args = ap.parse_args()

    ifc_path = Path(args.ifc_path)
    if not ifc_path.exists():
        print(f"File not found: {ifc_path}", file=sys.stderr)
        sys.exit(1)

    result = parse_ifc_deep(ifc_path)

    # Determine output path
    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = Path(__file__).resolve().parents[2] / 'data' / 'bim' / f'{ifc_path.stem}_deep'

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / 'ifc_data.json'
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=1)
    print(f"\nWrote: {json_path} ({json_path.stat().st_size / 1e6:.1f} MB)")

    if args.sqlite:
        db_path = out_dir / 'ifc_data.db'
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS elements (
                id INTEGER, guid TEXT, name TEXT, ifc_type TEXT,
                description TEXT, tag TEXT, storey TEXT,
                position TEXT, dimensions TEXT, materials TEXT,
                properties TEXT, classifications TEXT,
                has_geometry INTEGER, openings TEXT
            )
        """)
        for e in result['elements']:
            conn.execute(
                "INSERT INTO elements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e['id'], e['guid'], e['name'], e['ifc_type'],
                 e['description'], e['tag'], e['containment']['storey'],
                 json.dumps(e['position_m']), json.dumps(e['dimensions']),
                 json.dumps(e['materials']), json.dumps(e['properties']),
                 json.dumps(e['classifications']),
                 1 if e['has_geometry'] else 0,
                 json.dumps(e['opening_elements']))
            )
        conn.commit()
        conn.close()
        print(f"Wrote: {db_path}")

    print(f"\nDone. {result['statistics']['total_elements']} elements extracted.")


if __name__ == '__main__':
    main()
