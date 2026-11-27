import os
import sys
import unittest
from unittest.mock import patch

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from element_collector import CADElementCollector, get_object_by_handle, serialize_entity
from cad_controller import CADController
from server import CADService


class FakeAttribute:
    def __init__(self, tag: str, text: str):
        self.TagString = tag
        self.TextString = text


class FakeEntity:
    def __init__(self, handle: str, object_name: str, layer: str = "0", color: int = 256, **props):
        self.Handle = handle
        self.ObjectName = object_name
        self.Layer = layer
        self.Color = color
        for k, v in props.items():
            setattr(self, k, v)


class FakeBlockRef(FakeEntity):
    def __init__(
        self,
        handle: str,
        name: str,
        layer: str = "0",
        color: int = 256,
        effective_name: str = None,
        insertion_point=(0.0, 0.0, 0.0),
        attributes=None,
    ):
        super().__init__(
            handle,
            "AcDbBlockReference",
            layer=layer,
            color=color,
            Name=name,
            InsertionPoint=insertion_point,
            Rotation=0.0,
            XScaleFactor=1.0,
            YScaleFactor=1.0,
            ZScaleFactor=1.0,
            HasAttributes=bool(attributes),
        )
        if effective_name is not None:
            self.EffectiveName = effective_name
        self._attributes = attributes or []

    def GetAttributes(self):
        return tuple(self._attributes)


class FakeBlockDef:
    def __init__(self, name: str, entities=None, is_layout: bool = False, is_xref: bool = False, is_dynamic: bool = False):
        self.Name = name
        self._entities = list(entities or [])
        self.IsLayout = is_layout
        self.IsXRef = is_xref
        self.IsDynamicBlock = is_dynamic

    @property
    def Count(self):
        return len(self._entities)

    def __iter__(self):
        return iter(self._entities)


class FakeBlocks:
    def __init__(self, blocks):
        self._blocks = list(blocks)

    def Item(self, name: str):
        for blk in self._blocks:
            if blk.Name.lower() == name.lower():
                return blk
        raise KeyError(name)

    def __iter__(self):
        return iter(self._blocks)


class FakeLayer:
    def __init__(self, name: str, color: int = 7, on: bool = True, freeze: bool = False, lock: bool = False):
        self.Name = name
        self.Color = color
        self.LayerOn = on
        self.Freeze = freeze
        self.Lock = lock
        self.Plottable = True


class FakeLayers:
    def __init__(self, layers):
        self._layers = list(layers)

    def __iter__(self):
        return iter(self._layers)

    def Item(self, idx):
        return self._layers[idx]

    @property
    def Count(self):
        return len(self._layers)


class FakeLayout:
    def __init__(self, name: str, entities):
        self.Name = name
        self.Block = list(entities)


class FakeSelectionSet:
    def __init__(self, name: str, all_entities_with_layout, parent_collection):
        self.Name = name
        self._all = all_entities_with_layout
        self._parent = parent_collection
        self._items = []
        self.deleted = False

    def Select(self, mode, p1=None, p2=None, filter_type=None, filter_data=None):
        codes = list(filter_type) if filter_type is not None else []
        vals = list(filter_data) if filter_data is not None else []
        self._items = [
            ent for layout_name, ent in self._all
            if self._matches_dxf(layout_name, ent, codes, vals)
        ]

    @staticmethod
    def _entity_dxf(ent):
        mapping = {
            "AcDbLine": "LINE",
            "AcDbPolyline": "LWPOLYLINE",
            "AcDb2dPolyline": "POLYLINE",
            "AcDb3dPolyline": "POLYLINE",
            "AcDbCircle": "CIRCLE",
            "AcDbBlockReference": "INSERT",
            "AcDbText": "TEXT",
            "AcDbMText": "MTEXT",
        }
        return mapping.get(ent.ObjectName, ent.ObjectName.upper())

    def _matches_dxf(self, layout_name, ent, codes, vals):
        # Evaluate flat/simple <OR and <NOT groups emitted by CADElementCollector.
        i = 0
        while i < len(codes):
            c, v = codes[i], vals[i]
            if c == -4 and v == "<OR":
                or_match = False
                i += 1
                while i < len(codes) and not (codes[i] == -4 and vals[i] == "OR>"):
                    if self._single_match(layout_name, ent, codes[i], vals[i]):
                        or_match = True
                    i += 1
                if not or_match:
                    return False
            elif c == -4 and v == "<NOT":
                i += 1
                if self._single_match(layout_name, ent, codes[i], vals[i]):
                    return False
                i += 1  # skip NOT>
            else:
                if not self._single_match(layout_name, ent, c, v):
                    return False
            i += 1
        return True

    def _single_match(self, layout_name, ent, code, val):
        from fnmatch import fnmatchcase
        if code == 0:
            return self._entity_dxf(ent) == val
        if code == 8:
            return fnmatchcase(ent.Layer.lower(), str(val).lower())
        if code == 62:
            return ent.Color == val
        if code == 410:
            return layout_name.lower() == str(val).lower()
        return True

    @property
    def Count(self):
        return len(self._items)

    def Item(self, idx):
        return self._items[idx]

    def Delete(self):
        self.deleted = True
        self._parent._sets.pop(self.Name, None)


class FakeSelectionSets:
    def __init__(self, all_entities_with_layout):
        self._all = all_entities_with_layout
        self._sets = {}

    def Add(self, name: str):
        ss = FakeSelectionSet(name, self._all, self)
        self._sets[name] = ss
        return ss

    def Item(self, name: str):
        return self._sets[name]


class BrokenSelectionSets:
    def Add(self, name: str):
        raise RuntimeError("SelectionSet COM error")


class FakeDocument:
    def __init__(self, model_entities, paper_entities=None, blocks=None, layers=None, use_selection_sets=True):
        self.Name = "test_drawing.dwg"
        self.ModelSpace = list(model_entities)
        self.PaperSpace = list(paper_entities or [])
        self.Layouts = [
            FakeLayout("Model", self.ModelSpace),
            FakeLayout("Layout1", self.PaperSpace),
        ]
        all_with_layout = [("Model", e) for e in self.ModelSpace] + [("Layout1", e) for e in self.PaperSpace]
        self.SelectionSets = FakeSelectionSets(all_with_layout) if use_selection_sets else BrokenSelectionSets()
        self.Blocks = FakeBlocks(blocks or [])
        self.Layers = FakeLayers(layers or [FakeLayer("0")])
        self.ActiveLayer = self.Layers.Item(0)
        self._by_handle = {e.Handle: e for _, e in all_with_layout}

    def HandleToObject(self, handle: str):
        return self._by_handle[handle]

    def Regen(self, mode: int):
        pass


class ElementCollectorTests(unittest.TestCase):
    def setUp(self):
        self.entities = [
            FakeEntity("A1", "AcDbLine", layer="WALLS", color=1, StartPoint=(0, 0, 0), EndPoint=(10, 0, 0), Length=10.0),
            FakeEntity(
                "A2",
                "AcDbPolyline",
                layer="WALLS",
                color=256,
                Closed=True,
                Length=40.0,
                Area=100.0,
                Coordinates=(0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0),
            ),
            FakeEntity(
                "A3",
                "AcDb2dPolyline",
                layer="FURNITURE",
                color=3,
                Closed=False,
                Length=15.0,
                Coordinates=(1.0, 2.0, 0.0, 4.0, 6.0, 0.0),
            ),
            FakeBlockRef(
                "B1",
                name="Door-Single",
                layer="DOORS",
                insertion_point=(5.0, 0.0, 0.0),
                attributes=[FakeAttribute("MARK", "D101")],
            ),
            FakeBlockRef(
                "B2",
                name="*U42",
                effective_name="Door-Double",
                layer="DOORS",
                insertion_point=(12.0, 0.0, 0.0),
            ),
            FakeBlockRef("B3", name="Chair", layer="FURNITURE", insertion_point=(2.0, 3.0, 0.0)),
        ]
        self.paper_entities = [
            FakeEntity("P1", "AcDbText", layer="ANNO", TextString="PLAN", InsertionPoint=(1, 1, 0), Height=2.5),
        ]
        self.blocks = [
            FakeBlockDef("*Model_Space", is_layout=True),
            FakeBlockDef("Door-Single", entities=[self.entities[0]]),
            FakeBlockDef("Door-Double", entities=[self.entities[1]], is_dynamic=True),
            FakeBlockDef("Chair", entities=[self.entities[2]]),
        ]
        self.layers = [
            FakeLayer("0", color=7),
            FakeLayer("WALLS", color=1),
            FakeLayer("DOORS", color=2),
            FakeLayer("FURNITURE", color=3, lock=True),
        ]
        self.doc = FakeDocument(self.entities, self.paper_entities, self.blocks, self.layers)

    def _run_collector_collect(self, collector):
        # Patch _make_dxf_variants so SelectionSet path works without active Windows COM VARIANT
        with patch.object(collector, "_make_dxf_variants", side_effect=lambda c, v: (c, v)):
            return collector.collect

    def test_dxf_filter_construction(self):
        c = CADElementCollector(self.doc).in_space("model").of_type("polyline").on_layer("WALL*")
        codes, vals = c.build_dxf_filter()
        self.assertEqual(codes, [-4, 0, 0, -4, 8, 410])
        self.assertEqual(vals, ["<OR", "LWPOLYLINE", "POLYLINE", "OR>", "WALL*", "Model"])

        c_paper = CADElementCollector(self.doc).in_space("paper").of_block_name("Door*")
        codes_p, vals_p = c_paper.build_dxf_filter()
        self.assertEqual(codes_p, [0, -4, 410, -4])
        self.assertEqual(vals_p, ["INSERT", "<NOT", "Model", "NOT>"])

    def test_collect_polylines_selection_set_and_cleanup(self):
        collector = CADElementCollector(self.doc).in_space("model").of_type("polyline")
        with patch.object(collector, "_make_dxf_variants", side_effect=lambda c, v: (c, v)):
            res = collector.collect(include_geometry=True)
        self.assertEqual(res["query_mode"], "selection_set")
        self.assertEqual(res["total_matched"], 2)
        self.assertEqual([o["handle"] for o in res["objects"]], ["A2", "A3"])
        self.assertEqual(res["objects"][0]["vertex_count"], 4)
        self.assertEqual(res["objects"][0]["vertices"][1], [10.0, 0.0])
        self.assertEqual(res["objects"][1]["vertex_count"], 2)
        self.assertEqual(res["objects"][1]["vertices"][0], [1.0, 2.0, 0.0])
        # SelectionSet must be cleaned up
        self.assertEqual(len(self.doc.SelectionSets._sets), 0)

    def test_collect_blocks_including_dynamic_effective_name(self):
        collector = CADElementCollector(self.doc).in_space("model").of_block_name("Door*")
        with patch.object(collector, "_make_dxf_variants", side_effect=lambda c, v: (c, v)):
            res = collector.collect()
        self.assertEqual(res["total_matched"], 2)
        self.assertEqual([o["handle"] for o in res["objects"]], ["B1", "B2"])
        self.assertEqual(res["objects"][0]["attributes"], {"MARK": "D101"})
        self.assertEqual(res["objects"][1]["name"], "Door-Double")
        self.assertEqual(res["objects"][1]["raw_name"], "*U42")

    def test_pagination_limit_and_offset(self):
        collector = CADElementCollector(self.doc).in_space("model").limit(limit=2, offset=1)
        with patch.object(collector, "_make_dxf_variants", side_effect=lambda c, v: (c, v)):
            res = collector.collect(include_details=False)
        self.assertEqual(res["total_matched"], 6)
        self.assertEqual(res["returned_count"], 2)
        self.assertTrue(res["has_more"])
        self.assertEqual([o["handle"] for o in res["objects"]], ["A2", "A3"])

    def test_container_fallback_when_selection_set_fails(self):
        fallback_doc = FakeDocument(
            self.entities, self.paper_entities, self.blocks, self.layers, use_selection_sets=False
        )
        res = CADElementCollector(fallback_doc).in_space("paper").of_type("text").collect()
        self.assertEqual(res["query_mode"], "container_fallback")
        self.assertEqual(res["total_matched"], 1)
        self.assertEqual(res["objects"][0]["handle"], "P1")
        self.assertEqual(res["objects"][0]["text"], "PLAN")

    def test_summary_groups_counts(self):
        collector = CADElementCollector(self.doc).in_space("model")
        with patch.object(collector, "_make_dxf_variants", side_effect=lambda c, v: (c, v)):
            summary = collector.summarize()
        self.assertEqual(summary["matched"], 6)
        self.assertEqual(summary["by_type"]["AcDbBlockReference"], 3)
        self.assertEqual(summary["by_layer"]["DOORS"], 2)
        self.assertEqual(summary["by_block"]["Door-Double"], 1)

    def test_controller_and_service_tools_and_rename_blocks(self):
        ctrl = CADController()
        ctrl.app = object()
        ctrl.doc = self.doc

        with patch.object(CADElementCollector, "_make_dxf_variants", side_effect=lambda c, v: (c, v)):
            blocks_res = ctrl.list_blocks()
        self.assertTrue(blocks_res["success"])
        names = [b["name"] for b in blocks_res["blocks"]]
        self.assertEqual(names, ["Door-Single", "Door-Double", "Chair"])
        self.assertEqual(blocks_res["blocks"][1]["instance_count"], 1)

        layers_res = ctrl.list_layers(name_pattern="WALL*")
        self.assertTrue(layers_res["success"])
        self.assertEqual(layers_res["count"], 1)
        self.assertEqual(layers_res["layers"][0]["name"], "WALLS")

        obj_res = ctrl.get_object_by_handle("B1")
        self.assertTrue(obj_res["success"])
        self.assertEqual(obj_res["object"]["name"], "Door-Single")

        # Rename filtered blocks safely
        self.assertTrue(ctrl.rename_blocks(prefix="Pen", filter_block_name_prefix="Door"))
        renamed_names = [b.Name for b in self.doc.Blocks if not b.IsLayout]
        self.assertEqual(renamed_names, ["Pen-1", "Pen-2", "Chair"])

        # Service wrapper check
        svc = CADService()
        svc.controller = ctrl
        with patch.object(CADElementCollector, "_make_dxf_variants", side_effect=lambda c, v: (c, v)):
            listed = svc.list_objects(object_type="line", layer="WALLS")
        self.assertEqual(listed["total_matched"], 1)
        self.assertEqual(listed["objects"][0]["handle"], "A1")


if __name__ == "__main__":
    unittest.main()
