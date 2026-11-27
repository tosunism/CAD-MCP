"""Revit FilteredElementCollector-style query engine for AutoCAD COM documents.

Uses AutoCAD's native SelectionSet DXF group-code filtering (Quick Filter)
when available, with an automatic Python iteration fallback for unsupported
spaces, clone quirks, or Python-only predicates such as dynamic-block
``EffectiveName`` matching.
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

try:
    import pythoncom
    import win32com.client
except ImportError:  # Allow importing in non-COM test environments
    pythoncom = None
    win32com = None

logger = logging.getLogger("cad_element_collector")

AC_SELECTION_SET_ALL = 5

@dataclass(frozen=True)
class TypeSpec:
    friendly_name: str
    dxf_types: Tuple[str, ...]
    object_names: Tuple[str, ...]


TYPE_SPECS: Tuple[TypeSpec, ...] = (
    TypeSpec("line", ("LINE",), ("AcDbLine",)),
    TypeSpec("polyline", ("LWPOLYLINE", "POLYLINE"), ("AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline")),
    TypeSpec("lwpolyline", ("LWPOLYLINE",), ("AcDbPolyline",)),
    TypeSpec("2dpolyline", ("POLYLINE",), ("AcDb2dPolyline",)),
    TypeSpec("3dpolyline", ("POLYLINE",), ("AcDb3dPolyline",)),
    TypeSpec("circle", ("CIRCLE",), ("AcDbCircle",)),
    TypeSpec("arc", ("ARC",), ("AcDbArc",)),
    TypeSpec("ellipse", ("ELLIPSE",), ("AcDbEllipse",)),
    TypeSpec("spline", ("SPLINE",), ("AcDbSpline",)),
    TypeSpec("point", ("POINT",), ("AcDbPoint",)),
    TypeSpec("text", ("TEXT", "MTEXT"), ("AcDbText", "AcDbMText")),
    TypeSpec("dbtext", ("TEXT",), ("AcDbText",)),
    TypeSpec("mtext", ("MTEXT",), ("AcDbMText",)),
    TypeSpec("block_reference", ("INSERT",), ("AcDbBlockReference", "AcDbMInsertBlock")),
    TypeSpec("hatch", ("HATCH",), ("AcDbHatch",)),
    TypeSpec(
        "dimension",
        ("DIMENSION",),
        (
            "AcDbDimension",
            "AcDbAlignedDimension",
            "AcDbRotatedDimension",
            "AcDbRadialDimension",
            "AcDbDiametricDimension",
            "AcDb3PointAngularDimension",
            "AcDb2LineAngularDimension",
            "AcDbOrdinateDimension",
            "AcDbArcDimension",
        ),
    ),
    TypeSpec("leader", ("LEADER", "MULTILEADER"), ("AcDbLeader", "AcDbMLeader")),
    TypeSpec("3dsolid", ("3DSOLID",), ("AcDb3dSolid",)),
    TypeSpec("region", ("REGION",), ("AcDbRegion",)),
    TypeSpec("wipeout", ("WIPEOUT",), ("AcDbWipeout",)),
    TypeSpec("xline", ("XLINE",), ("AcDbXline",)),
    TypeSpec("ray", ("RAY",), ("AcDbRay",)),
    TypeSpec("viewport", ("VIEWPORT",), ("AcDbViewport",)),
    TypeSpec("image", ("IMAGE",), ("AcDbRasterImage",)),
)

TYPE_ALIAS_MAP: Dict[str, TypeSpec] = {spec.friendly_name: spec for spec in TYPE_SPECS}
TYPE_ALIAS_MAP.update({
    "pline": TYPE_ALIAS_MAP["polyline"],
    "lw_polyline": TYPE_ALIAS_MAP["lwpolyline"],
    "block": TYPE_ALIAS_MAP["block_reference"],
    "blocks": TYPE_ALIAS_MAP["block_reference"],
    "blockreference": TYPE_ALIAS_MAP["block_reference"],
    "block_ref": TYPE_ALIAS_MAP["block_reference"],
    "insert": TYPE_ALIAS_MAP["block_reference"],
    "dim": TYPE_ALIAS_MAP["dimension"],
    "mleader": TYPE_ALIAS_MAP["leader"],
    "solid": TYPE_ALIAS_MAP["3dsolid"],
    "raster": TYPE_ALIAS_MAP["image"],
})

OBJECT_NAME_TO_FRIENDLY: Dict[str, str] = {}
OBJECT_NAME_TO_DXF: Dict[str, Tuple[str, ...]] = {}
for _spec in TYPE_SPECS:
    for _obj_name in _spec.object_names:
        OBJECT_NAME_TO_FRIENDLY.setdefault(_obj_name.lower(), _spec.friendly_name)
        OBJECT_NAME_TO_DXF.setdefault(_obj_name.lower(), _spec.dxf_types)

# Prefer more specific friendly names for single-class lookups.
OBJECT_NAME_TO_FRIENDLY["acdbpolyline"] = "polyline"
OBJECT_NAME_TO_FRIENDLY["acdb2dpolyline"] = "2dpolyline"
OBJECT_NAME_TO_FRIENDLY["acdb3dpolyline"] = "3dpolyline"
OBJECT_NAME_TO_FRIENDLY["acdbtext"] = "text"
OBJECT_NAME_TO_FRIENDLY["acdbmtext"] = "mtext"


def _safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely read a COM property that may be missing or raise an error."""
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _to_point_list(value: Any, precision: int = 6) -> Optional[List[float]]:
    """Convert a COM coordinate tuple/sequence into a rounded JSON-safe list."""
    if value is None:
        return None
    try:
        return [round(float(v), precision) for v in value]
    except Exception:
        return None


def _matches_pattern(value: Optional[str], pattern: Optional[str]) -> bool:
    """Case-insensitive exact or wildcard (*, ?) match."""
    if pattern is None:
        return True
    if value is None:
        return False
    val_l = value.lower()
    pat_l = pattern.lower()
    if "*" in pat_l or "?" in pat_l:
        return fnmatchcase(val_l, pat_l)
    return val_l == pat_l


def _get_block_ref_names(entity: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return (effective_name, raw_name) for a block reference entity."""
    raw_name = _safe_getattr(entity, "Name")
    effective_name = _safe_getattr(entity, "EffectiveName") or raw_name
    return effective_name, raw_name


def _normalize_object_type_inputs(
    object_types: Union[str, Sequence[str]]
) -> Tuple[List[str], Set[str]]:
    """Resolve user-provided type names into (dxf_types, allowed_object_names_lower).

    ``allowed_object_names_lower`` is empty when raw DXF types are supplied
    that do not have a known ``AcDb*`` mapping, in which case DXF filtering
    or fallback suffix checks handle matching.
    """
    if isinstance(object_types, str):
        raw_list = [object_types]
    else:
        raw_list = list(object_types)

    dxf_types: List[str] = []
    object_names_lower: Set[str] = set()

    for raw in raw_list:
        if not raw:
            continue
        cleaned = str(raw).strip()
        key = cleaned.lower().replace("-", "_")

        if key in TYPE_ALIAS_MAP:
            spec = TYPE_ALIAS_MAP[key]
            for dxf in spec.dxf_types:
                if dxf not in dxf_types:
                    dxf_types.append(dxf)
            object_names_lower.update(name.lower() for name in spec.object_names)
        elif key.startswith("acdb"):
            object_names_lower.add(key)
            mapped_dxf = OBJECT_NAME_TO_DXF.get(key)
            if mapped_dxf:
                for dxf in mapped_dxf:
                    if dxf not in dxf_types:
                        dxf_types.append(dxf)
        else:
            upper_dxf = cleaned.upper()
            if upper_dxf not in dxf_types:
                dxf_types.append(upper_dxf)
            # Also allow matching friendly aliases via reverse lookup if any
            for spec in TYPE_SPECS:
                if upper_dxf in spec.dxf_types:
                    object_names_lower.update(name.lower() for name in spec.object_names)

    return dxf_types, object_names_lower


def serialize_entity(
    entity: Any,
    include_details: bool = True,
    include_geometry: bool = False,
    include_attributes: bool = True,
) -> Dict[str, Any]:
    """Serialize a COM CAD entity into a compact, JSON-safe dictionary."""
    object_name = _safe_getattr(entity, "ObjectName", "Unknown") or "Unknown"
    obj_lower = object_name.lower()
    friendly_type = OBJECT_NAME_TO_FRIENDLY.get(obj_lower)
    if friendly_type is None and "dimension" in obj_lower:
        friendly_type = "dimension"
    if friendly_type is None:
        friendly_type = object_name

    data: Dict[str, Any] = {
        "handle": _safe_getattr(entity, "Handle"),
        "object_name": object_name,
        "entity_type": friendly_type,
        "layer": _safe_getattr(entity, "Layer"),
        "color": _safe_getattr(entity, "Color"),
    }

    if not include_details and not include_geometry:
        return data

    if obj_lower in ("acdbblockreference", "acdbminsertblock"):
        eff_name, raw_name = _get_block_ref_names(entity)
        data["name"] = eff_name
        if raw_name and eff_name and raw_name != eff_name:
            data["raw_name"] = raw_name
        data["insertion_point"] = _to_point_list(_safe_getattr(entity, "InsertionPoint"))
        rotation = _safe_getattr(entity, "Rotation")
        if rotation is not None:
            data["rotation_rad"] = round(float(rotation), 6)
        x_scale = _safe_getattr(entity, "XScaleFactor")
        y_scale = _safe_getattr(entity, "YScaleFactor")
        z_scale = _safe_getattr(entity, "ZScaleFactor")
        if x_scale is not None:
            data["scale"] = [
                round(float(x_scale), 6),
                round(float(y_scale if y_scale is not None else x_scale), 6),
                round(float(z_scale if z_scale is not None else 1.0), 6),
            ]
        has_attrs = bool(_safe_getattr(entity, "HasAttributes", False))
        data["has_attributes"] = has_attrs
        if has_attrs and include_attributes:
            attrs: Dict[str, str] = {}
            try:
                for attr in entity.GetAttributes():
                    tag = _safe_getattr(attr, "TagString")
                    val = _safe_getattr(attr, "TextString", "")
                    if tag is not None:
                        attrs[str(tag)] = str(val)
            except Exception:
                pass
            if attrs:
                data["attributes"] = attrs

    elif obj_lower == "acdbline":
        data["start_point"] = _to_point_list(_safe_getattr(entity, "StartPoint"))
        data["end_point"] = _to_point_list(_safe_getattr(entity, "EndPoint"))
        length = _safe_getattr(entity, "Length")
        if length is not None:
            data["length"] = round(float(length), 6)

    elif obj_lower == "acdbcircle":
        data["center"] = _to_point_list(_safe_getattr(entity, "Center"))
        radius = _safe_getattr(entity, "Radius")
        if radius is not None:
            data["radius"] = round(float(radius), 6)
        area = _safe_getattr(entity, "Area")
        if area is not None:
            data["area"] = round(float(area), 6)

    elif obj_lower == "acdbarc":
        data["center"] = _to_point_list(_safe_getattr(entity, "Center"))
        radius = _safe_getattr(entity, "Radius")
        if radius is not None:
            data["radius"] = round(float(radius), 6)
        start_angle = _safe_getattr(entity, "StartAngle")
        end_angle = _safe_getattr(entity, "EndAngle")
        if start_angle is not None:
            data["start_angle_rad"] = round(float(start_angle), 6)
        if end_angle is not None:
            data["end_angle_rad"] = round(float(end_angle), 6)
        arc_len = _safe_getattr(entity, "ArcLength")
        if arc_len is not None:
            data["arc_length"] = round(float(arc_len), 6)

    elif obj_lower == "acdbellipse":
        data["center"] = _to_point_list(_safe_getattr(entity, "Center"))
        data["major_axis"] = _to_point_list(_safe_getattr(entity, "MajorAxis"))
        ratio = _safe_getattr(entity, "RadiusRatio")
        if ratio is not None:
            data["radius_ratio"] = round(float(ratio), 6)

    elif obj_lower in ("acdbpolyline", "acdb2dpolyline", "acdb3dpolyline"):
        closed = _safe_getattr(entity, "Closed")
        if closed is not None:
            data["closed"] = bool(closed)
        length = _safe_getattr(entity, "Length")
        if length is not None:
            data["length"] = round(float(length), 6)
        area = _safe_getattr(entity, "Area")
        if area is not None:
            data["area"] = round(float(area), 6)
        coords = _safe_getattr(entity, "Coordinates")
        if coords is not None:
            stride = 2 if obj_lower == "acdbpolyline" else 3
            try:
                coord_list = [round(float(c), 6) for c in coords]
                data["vertex_count"] = len(coord_list) // stride
                if include_geometry:
                    data["vertices"] = [
                        coord_list[i : i + stride]
                        for i in range(0, len(coord_list), stride)
                    ]
            except Exception:
                pass

    elif obj_lower in ("acdbtext", "acdbmtext"):
        data["text"] = _safe_getattr(entity, "TextString")
        data["insertion_point"] = _to_point_list(_safe_getattr(entity, "InsertionPoint"))
        height = _safe_getattr(entity, "Height")
        if height is not None:
            data["height"] = round(float(height), 6)

    elif obj_lower == "acdbhatch":
        data["pattern_name"] = _safe_getattr(entity, "PatternName")
        area = _safe_getattr(entity, "Area")
        if area is not None:
            data["area"] = round(float(area), 6)

    elif "dimension" in obj_lower:
        measurement = _safe_getattr(entity, "Measurement")
        if measurement is not None:
            data["measurement"] = round(float(measurement), 6)
        text_override = _safe_getattr(entity, "TextOverride")
        if text_override:
            data["text_override"] = text_override

    return data


def get_object_by_handle(
    doc: Any,
    handle: str,
    include_details: bool = True,
    include_geometry: bool = True,
    include_attributes: bool = True,
) -> Dict[str, Any]:
    """Retrieve and serialize a single CAD entity by its persistent DWG handle."""
    entity = doc.HandleToObject(handle)
    return serialize_entity(
        entity,
        include_details=include_details,
        include_geometry=include_geometry,
        include_attributes=include_attributes,
    )


class CADElementCollector:
    """Fluent, Revit FilteredElementCollector-style query builder for AutoCAD COM."""

    def __init__(self, doc: Any) -> None:
        self._doc = doc
        self._space: str = "model"
        self._dxf_types: List[str] = []
        self._object_names_lower: Set[str] = set()
        self._layer: Optional[str] = None
        self._block_name: Optional[str] = None
        self._color: Optional[int] = None
        self._limit: int = 50
        self._offset: int = 0

    def in_space(self, space: Optional[str] = "model") -> "CADElementCollector":
        """Scope query to ``'model'``, ``'paper'``, ``'all'``, or a layout name."""
        self._space = (space or "model").strip()
        return self

    def of_type(self, object_type: str) -> "CADElementCollector":
        """Filter to a single object type (friendly alias, DXF name, or AcDb name)."""
        return self.of_types([object_type])

    def of_types(self, object_types: Union[str, Sequence[str]]) -> "CADElementCollector":
        """Filter to one or more object types."""
        dxf_types, obj_names = _normalize_object_type_inputs(object_types)
        self._dxf_types = dxf_types
        self._object_names_lower = obj_names
        return self

    def on_layer(self, layer: Optional[str]) -> "CADElementCollector":
        """Filter by layer name (case-insensitive; supports ``*`` and ``?`` wildcards)."""
        self._layer = layer.strip() if layer else None
        return self

    def of_block_name(self, block_name: Optional[str]) -> "CADElementCollector":
        """Filter block references by block name or dynamic block EffectiveName."""
        self._block_name = block_name.strip() if block_name else None
        return self

    def with_color(self, color: Optional[int]) -> "CADElementCollector":
        """Filter by AutoCAD Color Index (ACI integer)."""
        self._color = int(color) if color is not None else None
        return self

    def limit(self, limit: int = 50, offset: int = 0) -> "CADElementCollector":
        """Paginate results; ``limit`` is clamped to [1, 500]."""
        self._limit = max(1, min(int(limit), 500))
        self._offset = max(0, int(offset))
        return self

    def _effective_dxf_types(self) -> List[str]:
        """Return DXF types to apply, narrowing to INSERT when block_name is set."""
        if self._block_name and not self._dxf_types and not self._object_names_lower:
            return ["INSERT"]
        return list(self._dxf_types)

    def _effective_object_names(self) -> Set[str]:
        if self._block_name and not self._dxf_types and not self._object_names_lower:
            return {"acdbblockreference", "acdbminsertblock"}
        return set(self._object_names_lower)

    def _needs_python_post_filter(self) -> bool:
        """Whether SelectionSet results still require per-entity Python checks."""
        if self._block_name is not None:
            return True
        # DXF code 62 is often omitted on entities with ByLayer (256) color.
        if self._color == 256:
            return True
        # An explicit AcDb* filter may share a DXF name (e.g. AcDb2dPolyline vs AcDb3dPolyline).
        if self._object_names_lower and not self._dxf_types:
            return True
        if self._object_names_lower & {"acdb2dpolyline", "acdb3dpolyline", "acdbminsertblock"}:
            return True
        return False

    def build_dxf_filter(self) -> Tuple[List[int], List[Any]]:
        """Build AutoCAD SelectionSet DXF ``(FilterType, FilterData)`` lists."""
        codes: List[int] = []
        values: List[Any] = []

        dxf_types = self._effective_dxf_types()
        if len(dxf_types) == 1:
            codes.append(0)
            values.append(dxf_types[0])
        elif len(dxf_types) > 1:
            codes.append(-4)
            values.append("<OR")
            for dxf_type in dxf_types:
                codes.append(0)
                values.append(dxf_type)
            codes.append(-4)
            values.append("OR>")

        if self._layer:
            codes.append(8)
            values.append(self._layer)

        # Avoid DXF code 62 when filtering for ByLayer (256), as ByLayer often has no 62 group.
        if self._color is not None and self._color != 256:
            codes.append(62)
            values.append(int(self._color))

        space_lower = self._space.lower()
        if space_lower == "model":
            codes.append(410)
            values.append("Model")
        elif space_lower == "paper":
            codes.extend([-4, 410, -4])
            values.extend(["<NOT", "Model", "NOT>"])
        elif space_lower != "all":
            codes.append(410)
            values.append(self._space)

        return codes, values

    def _matches_python_filters(self, entity: Any, check_quick_filters: bool) -> bool:
        """Evaluate Python-only predicates (and quick filters in fallback mode)."""
        allowed_obj_names = self._effective_object_names()
        if allowed_obj_names:
            obj_name = (_safe_getattr(entity, "ObjectName", "") or "").lower()
            if obj_name not in allowed_obj_names:
                return False
        elif check_quick_filters and self._dxf_types:
            obj_name = (_safe_getattr(entity, "ObjectName", "") or "").lower()
            dxf_candidates = OBJECT_NAME_TO_DXF.get(obj_name, ())
            if not any(d in self._dxf_types for d in dxf_candidates):
                return False

        if self._block_name is not None:
            obj_name = (_safe_getattr(entity, "ObjectName", "") or "").lower()
            if obj_name not in ("acdbblockreference", "acdbminsertblock"):
                return False
            eff_name, raw_name = _get_block_ref_names(entity)
            if not (_matches_pattern(eff_name, self._block_name) or _matches_pattern(raw_name, self._block_name)):
                return False

        if check_quick_filters and self._layer:
            if not _matches_pattern(_safe_getattr(entity, "Layer"), self._layer):
                return False

        if self._color is not None and (check_quick_filters or self._color == 256):
            if _safe_getattr(entity, "Color") != self._color:
                return False

        return True

    def _make_dxf_variants(self, codes: List[int], values: List[Any]) -> Tuple[Any, Any]:
        if win32com is None or pythoncom is None:
            raise RuntimeError("win32com/pythoncom is not available")
        filter_type = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I2, codes)
        filter_data = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, values)
        return filter_type, filter_data

    def _open_selection_set(self) -> Tuple[Any, str]:
        """Create and populate a temporary AutoCAD SelectionSet using DXF filters."""
        ss_name = f"_MCP_COL_{uuid.uuid4().hex[:8]}"
        ss_collection = self._doc.SelectionSets
        try:
            ss_collection.Item(ss_name).Delete()
        except Exception:
            pass

        ss = ss_collection.Add(ss_name)
        try:
            codes, values = self.build_dxf_filter()
            if codes:
                filter_type, filter_data = self._make_dxf_variants(codes, values)
                ss.Select(AC_SELECTION_SET_ALL, None, None, filter_type, filter_data)
            else:
                ss.Select(AC_SELECTION_SET_ALL)
            return ss, ss_name
        except Exception:
            try:
                ss.Delete()
            except Exception:
                pass
            raise

    def _iter_fallback_containers(self) -> List[Any]:
        """Return COM container collections matching ``self._space`` for fallback iteration."""
        space_lower = self._space.lower()
        containers: List[Any] = []
        if space_lower == "model":
            if _safe_getattr(self._doc, "ModelSpace") is not None:
                containers.append(self._doc.ModelSpace)
            return containers

        layouts = _safe_getattr(self._doc, "Layouts")
        if layouts is not None:
            try:
                for layout in layouts:
                    layout_name = _safe_getattr(layout, "Name", "") or ""
                    if space_lower == "all":
                        containers.append(layout.Block)
                    elif space_lower == "paper" and layout_name.lower() != "model":
                        containers.append(layout.Block)
                    elif layout_name.lower() == space_lower:
                        containers.append(layout.Block)
                if containers:
                    return containers
            except Exception:
                pass

        if space_lower in ("all", "model") and _safe_getattr(self._doc, "ModelSpace") is not None:
            containers.append(self._doc.ModelSpace)
        if space_lower in ("all", "paper") and _safe_getattr(self._doc, "PaperSpace") is not None:
            containers.append(self._doc.PaperSpace)
        return containers

    def _iterate_fallback_entities(self) -> Iterable[Any]:
        for container in self._iter_fallback_containers():
            for entity in container:
                yield entity

    def collect(
        self,
        include_details: bool = True,
        include_geometry: bool = False,
        include_attributes: bool = True,
    ) -> Dict[str, Any]:
        """Execute the query and return paginated entity results plus metadata."""
        objects: List[Dict[str, Any]] = []
        total_matched = 0
        query_mode = "selection_set"

        try:
            ss, _ = self._open_selection_set()
            try:
                raw_count = int(ss.Count)
                if not self._needs_python_post_filter():
                    total_matched = raw_count
                    end = min(self._offset + self._limit, raw_count)
                    for idx in range(self._offset, end):
                        entity = ss.Item(idx)
                        objects.append(
                            serialize_entity(
                                entity,
                                include_details=include_details,
                                include_geometry=include_geometry,
                                include_attributes=include_attributes,
                            )
                        )
                else:
                    for idx in range(raw_count):
                        entity = ss.Item(idx)
                        if not self._matches_python_filters(entity, check_quick_filters=False):
                            continue
                        if self._offset <= total_matched < self._offset + self._limit:
                            objects.append(
                                serialize_entity(
                                    entity,
                                    include_details=include_details,
                                    include_geometry=include_geometry,
                                    include_attributes=include_attributes,
                                )
                            )
                        total_matched += 1
            finally:
                try:
                    ss.Delete()
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("SelectionSet query unavailable, falling back to container iteration: %s", exc)
            query_mode = "container_fallback"
            for entity in self._iterate_fallback_entities():
                if not self._matches_python_filters(entity, check_quick_filters=True):
                    continue
                if self._offset <= total_matched < self._offset + self._limit:
                    objects.append(
                        serialize_entity(
                            entity,
                            include_details=include_details,
                            include_geometry=include_geometry,
                            include_attributes=include_attributes,
                        )
                    )
                total_matched += 1

        return {
            "total_matched": total_matched,
            "returned_count": len(objects),
            "offset": self._offset,
            "limit": self._limit,
            "has_more": (self._offset + len(objects)) < total_matched,
            "space": self._space,
            "query_mode": query_mode,
            "objects": objects,
        }

    def count(self) -> int:
        """Return total matching entity count without serializing entity details."""
        try:
            ss, _ = self._open_selection_set()
            try:
                raw_count = int(ss.Count)
                if not self._needs_python_post_filter():
                    return raw_count
                matched = 0
                for idx in range(raw_count):
                    if self._matches_python_filters(ss.Item(idx), check_quick_filters=False):
                        matched += 1
                return matched
            finally:
                try:
                    ss.Delete()
                except Exception:
                    pass
        except Exception:
            matched = 0
            for entity in self._iterate_fallback_entities():
                if self._matches_python_filters(entity, check_quick_filters=True):
                    matched += 1
            return matched

    def summarize(self, max_scan: int = 5000) -> Dict[str, Any]:
        """Summarize matching entities by type, layer, and block name."""
        max_scan = max(1, int(max_scan))
        by_type: Dict[str, int] = {}
        by_layer: Dict[str, int] = {}
        by_block: Dict[str, int] = {}
        total_candidates = 0
        matched = 0
        scanned = 0
        truncated = False
        query_mode = "selection_set"

        def _tally(entity: Any) -> None:
            obj_name = _safe_getattr(entity, "ObjectName", "Unknown") or "Unknown"
            layer_name = _safe_getattr(entity, "Layer", "") or ""
            by_type[obj_name] = by_type.get(obj_name, 0) + 1
            by_layer[layer_name] = by_layer.get(layer_name, 0) + 1
            if obj_name.lower() in ("acdbblockreference", "acdbminsertblock"):
                eff_name, _ = _get_block_ref_names(entity)
                if eff_name:
                    by_block[eff_name] = by_block.get(eff_name, 0) + 1

        try:
            ss, _ = self._open_selection_set()
            try:
                total_candidates = int(ss.Count)
                needs_py = self._needs_python_post_filter()
                scan_limit = min(total_candidates, max_scan)
                truncated = total_candidates > max_scan
                for idx in range(scan_limit):
                    entity = ss.Item(idx)
                    scanned += 1
                    if needs_py and not self._matches_python_filters(entity, check_quick_filters=False):
                        continue
                    matched += 1
                    _tally(entity)
            finally:
                try:
                    ss.Delete()
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("SelectionSet summary unavailable, falling back to container iteration: %s", exc)
            query_mode = "container_fallback"
            for entity in self._iterate_fallback_entities():
                if scanned >= max_scan:
                    truncated = True
                    break
                scanned += 1
                total_candidates += 1
                if not self._matches_python_filters(entity, check_quick_filters=True):
                    continue
                matched += 1
                _tally(entity)

        return {
            "space": self._space,
            "query_mode": query_mode,
            "total_candidates": total_candidates,
            "scanned": scanned,
            "matched": matched,
            "truncated": truncated,
            "by_type": dict(sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_layer": dict(sorted(by_layer.items(), key=lambda kv: (-kv[1], kv[0]))),
            "by_block": dict(sorted(by_block.items(), key=lambda kv: (-kv[1], kv[0]))),
        }
