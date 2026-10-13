#!/usr/bin/env python3
"""Behavior regressions for the bundled mechanical checks and SVG renderer."""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLAIM = load("claim_lint")
FIGURE = load("patent_figure_svg")
NS = {"s": "http://www.w3.org/2000/svg"}
BASE = "1.一种数据处理方法，其特征在于，获取数据并输出结果。"


def report_codes(text, **kwargs):
    return {item["code"] for item in CLAIM.lint_text(text, **kwargs)["issues"]}


def svg_tree(spec):
    return ET.fromstring(FIGURE.build_diagram(spec))


def visible_text(tree):
    return "".join("".join(el.itertext()) for el in tree.findall(".//s:text", NS))


def assert_canvas(test, tree):
    ox, oy, w, h = map(float, tree.get("viewBox").split())
    for group in tree.findall("s:g", NS):
        if not group.get("data-node-id"):
            continue
        shape = group.find("s:rect", NS)
        if shape is not None:
            x, y, nw, nh = (float(shape.get(key)) for key in ("x", "y", "width", "height"))
            test.assertGreaterEqual(x, ox)
            test.assertGreaterEqual(y, oy)
            test.assertLessEqual(x + nw, ox + w)
            test.assertLessEqual(y + nh, oy + h)
    for edge in tree.findall("s:polyline", NS):
        for token in edge.get("points").split():
            x, y = map(float, token.split(","))
            test.assertTrue(ox <= x <= ox + w and oy <= y <= oy + h)


class ClaimTests(unittest.TestCase):
    def test_definite_claim(self):
        self.assertEqual(CLAIM.lint_text(BASE)["issues"], [])

    def test_technical_compounds(self):
        text = "1.一种判断方法，其特征在于，比较相等、等价、不等式和基本块。"
        self.assertNotIn("wording_review", report_codes(text))

    def test_full_review_list_is_reported(self):
        for term in CLAIM.load_rules()["review_terms"]:
            with self.subTest(term=term):
                self.assertIn("wording_review", report_codes(f"1.一种方法，其特征在于，{term}执行处理。"))

    def test_sentence_end_and_multiple_stops(self):
        for body in ["1.一种方法。其特征在于获取数据", "1.获取数据。输出结果。", "1.获取数据"]:
            with self.subTest(body=body):
                self.assertIn("full_stop", report_codes(body))

    def test_decimal_does_not_split_claim(self):
        result = CLAIM.lint_text("1.一种方法，其特征在于，阈值设置为0.5；\n3.14为常数。")
        self.assertEqual(len(result["claims"]), 1)
        self.assertEqual(result["error_count"], 0)

    def test_duplicate_and_gap(self):
        self.assertIn("duplicate_number", report_codes(BASE + "\n" + BASE))
        self.assertIn("numbering_order", report_codes(BASE + "\n3.输出数据。"))

    def test_missing_reference(self):
        self.assertIn("unknown_reference", report_codes(BASE + "\n2.根据权利要求3所述的方法，其特征在于，过滤数据。"))

    def test_forward_and_self_reference(self):
        text = BASE + "\n2.根据权利要求3所述的方法，其特征在于，过滤数据。\n3.根据权利要求3所述的方法，其特征在于，输出数据。"
        self.assertIn("nonprior_reference", report_codes(text))

    def test_multiple_alternative_and_range(self):
        text = BASE + "\n2.根据权利要求1所述的方法，其特征在于，过滤数据。\n3.根据权利要求1或2所述的方法，其特征在于，输出数据。"
        self.assertEqual(CLAIM.lint_text(text)["error_count"], 0)
        self.assertEqual(CLAIM.lint_text(text.replace("1或2", "1至2中任一项"))["error_count"], 0)

    def test_multiple_requires_alternative(self):
        text = BASE + "\n2.过滤数据。\n3.根据权利要求1和2所述的方法，其特征在于，输出数据。"
        self.assertIn("multiple_reference_not_alternative", report_codes(text))

    def test_multiple_on_multiple(self):
        text = BASE + "\n2.过滤数据。\n3.根据权利要求1或2所述的方法，其特征在于，输出数据。\n4.根据权利要求1或3所述的方法，其特征在于，输出数据。"
        self.assertIn("multiple_on_multiple", report_codes(text))

    def test_section_stops_before_specification(self):
        text = "权利要求书\n" + BASE + "\n说明书\n1.说明段落。"
        self.assertEqual(len(CLAIM.parse_claims(text)), 1)

    def test_abstract_includes_punctuation(self):
        text = "一、说明书摘要\n" + "技" * 299 + "。\n二、摘要附图\n图1\n三、权利要求书\n" + BASE + "\n四、说明书\n技术领域"
        result = CLAIM.lint_text(text, patent=True)
        self.assertEqual(result["abstract_character_count"], 300)
        self.assertNotIn("abstract_length", report_codes(text, patent=True))
        self.assertIn("abstract_length", report_codes(text.replace("。\n二、", "术。\n二、"), patent=True))

    def test_cli_json_strict_and_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claims.txt"
            path.write_text(BASE.replace("获取", "可能获取"), encoding="utf-8-sig")
            cmd = [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "claim_lint.py"), str(path), "--json"]
            result = subprocess.run(cmd, cwd=tmp, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0)
            self.assertGreater(json.loads(result.stdout)["warning_count"], 0)
            result = subprocess.run(cmd + ["--strict"], cwd=tmp, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 1)

    def test_bracketed_references_are_not_lost(self):
        for token in ("（3）", "(3)", "[3]", "【3】"):
            text = BASE + f"\n2.根据权利要求{token}所述的方法，其特征在于，过滤数据。"
            with self.subTest(token=token):
                self.assertIn("unknown_reference", report_codes(text))

    def test_repeated_reference_keyword_is_fully_parsed(self):
        text = BASE + "\n2.根据权利要求1和权利要求3所述的方法，其特征在于，输出数据。"
        result = CLAIM.lint_text(text)
        self.assertEqual(result["claims"][1]["references"], [1, 3])
        self.assertIn("unknown_reference", report_codes(text))

    def test_unrecognized_reference_is_explicit(self):
        text = BASE + "\n2.根据权利要求一所述的方法，其特征在于，过滤数据。"
        self.assertIn("reference_parse_incomplete", report_codes(text))

    def test_arbitrary_reference_suffix_is_not_silently_truncated(self):
        text = BASE + "\n2.根据权利要求1或者其他方法所述的方法，其特征在于，过滤数据。"
        self.assertIn("reference_parse_incomplete", report_codes(text))

    def test_valid_repeated_and_any_reference(self):
        text = BASE + "\n2.过滤数据。\n3.根据权利要求1或者权利要求2中任意一项所述的方法，其特征在于，输出数据。"
        self.assertEqual(CLAIM.lint_text(text)["error_count"], 0)

    def test_bracket_mismatch_and_bad_range_are_explicit(self):
        for token, code in (("(1]", "reference_parse_incomplete"), ("3至1", "reference_range")):
            with self.subTest(token=token):
                text = BASE + f"\n2.根据权利要求{token}所述的方法，其特征在于，输出数据。"
                self.assertIn(code, report_codes(text))


class FigureTests(unittest.TestCase):
    def test_example_caption_and_number(self):
        spec = json.loads((ROOT / "assets" / "figure-spec-example.json").read_text(encoding="utf-8"))
        tree = svg_tree(spec)
        self.assertIn(spec["figure_no"], visible_text(tree))
        self.assertIn(spec["title"], visible_text(tree))
        assert_canvas(self, tree)

    def test_mixed_positions(self):
        tree = svg_tree({"diagram_type": "block", "nodes": [
            {"id": "a", "label": "A", "x": 40, "y": 40},
            {"id": "b", "label": "B"}], "edges": [["a", "b"]]})
        assert_canvas(self, tree)

    def test_manual_flow_and_small_requested_canvas(self):
        tree = svg_tree({"diagram_type": "flowchart", "width": 10, "height": 10,
                         "nodes": [{"id": "a", "label": "A", "y": 800}]})
        assert_canvas(self, tree)
        self.assertGreater(float(tree.get("height")), 864)

    def test_branch_label_and_xml_escaping(self):
        tree = svg_tree({"diagram_type": "flowchart", "nodes": [
            {"id": "a", "label": "数值 < 阈值 & 条件", "shape": "decision"},
            {"id": "b", "label": "处理"}], "edges": [{"source": "a", "target": "b", "label": "是"}]})
        self.assertIn("数值 < 阈值 & 条件", visible_text(tree))
        self.assertIn("是", visible_text(tree))
        assert_canvas(self, tree)

    def test_return_route_and_negative_coordinates(self):
        tree = svg_tree({"diagram_type": "block", "nodes": [
            {"id": "a", "label": "A", "x": -100, "y": -40},
            {"id": "b", "label": "B", "x": 300, "y": -40}],
            "edges": [{"source": "b", "target": "a", "route": "bottom_return", "label": "反馈"}]})
        self.assertLess(float(tree.get("viewBox").split()[0]), 0)
        assert_canvas(self, tree)

    def test_annotations_and_manual_routes_fit(self):
        tree = svg_tree({"diagram_type": "block", "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                         "edges": [{"source": "a", "target": "b", "source_port": "bottom", "target_port": "bottom",
                                    "points": [[170, 148], [170, 400], [1000, 400], [1000, 300], [478, 300], [478, 148]]}],
                         "annotations": [{"x": 1300, "y": 700, "text": "输入"}]})
        assert_canvas(self, tree)
        self.assertGreater(float(tree.get("width")), 1300)
        self.assertGreater(float(tree.get("height")), 700)

    def test_long_label_fits_expanded_box(self):
        tree = svg_tree({"diagram_type": "flowchart", "nodes": [{"id": "a", "label": "输入数据预处理" * 12}]})
        group = tree.find('s:g[@data-node-id="a"]', NS)
        rect = group.find("s:rect", NS)
        y, h = float(rect.get("y")), float(rect.get("height"))
        self.assertGreater(h, 64)
        for span in group.findall(".//s:tspan", NS):
            self.assertTrue(y <= float(span.get("y")) <= y + h)

    def test_default_shapes_and_monochrome(self):
        tree = svg_tree({"diagram_type": "flowchart", "nodes": [
            {"id": "a", "label": "开始", "shape": "terminator"},
            {"id": "b", "label": "处理"}]})
        self.assertGreater(float(tree.find('s:g[@data-node-id="a"]/s:rect', NS).get("rx")), 0)
        self.assertEqual(float(tree.find('s:g[@data-node-id="b"]/s:rect', NS).get("rx")), 0)
        for elem in tree.iter():
            for key in ("fill", "stroke"):
                if elem.get(key):
                    self.assertIn(elem.get(key), {"#000", "#fff", "none"})

    def test_duplicate_unknown_and_empty_nodes_fail(self):
        for spec in [
            {"diagram_type": "block", "nodes": []},
            {"diagram_type": "block", "nodes": [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}]},
            {"diagram_type": "block", "nodes": [{"id": "a", "label": "A"}], "edges": [["a", "missing"]]},
            {"diagram_type": "block", "nodes": [{"id": "a", "label": "A", "w": 0}]},
            {"diagram_type": "block", "nodes": [{"id": "a", "label": "A"}], "edges": [{"source": "a", "target": "a", "points": [[1, 2]]}]},
        ]:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                FIGURE.build_diagram(spec)

    def test_skip_edge_avoids_middle_node(self):
        spec = {"diagram_type": "flowchart", "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
                "edges": [["a", "c"]]}
        tree = svg_tree(spec)
        middle = tree.find('s:g[@data-node-id="b"]/s:rect', NS)
        obstacle = {"id": "b", **{key: float(middle.get(name)) for key, name in [("x", "x"), ("y", "y"), ("w", "width"), ("h", "height")]}}
        points = [tuple(map(float, s.split(","))) for s in tree.find("s:polyline", NS).get("points").split()]
        self.assertFalse(FIGURE.intersects(points, [obstacle], set()))

    def test_cli_cwd_and_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, out = Path(tmp) / "spec.json", Path(tmp) / "diagram.svg"
            path.write_text(json.dumps({"diagram_type": "block", "nodes": [{"id": "a", "label": "A"}]}), encoding="utf-8-sig")
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "patent_figure_svg.py"), str(path), str(out)],
                                    cwd=tmp, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            ET.parse(out)

    def test_branch_example_preserves_all_labels(self):
        spec = json.loads((ROOT / "assets" / "figure-branch-example.json").read_text(encoding="utf-8"))
        tree = svg_tree(spec)
        self.assertEqual(len(tree.findall("s:polyline", NS)), len(spec["edges"]))
        for label in ("是", "否", "反馈"):
            self.assertIn(label, visible_text(tree))
        assert_canvas(self, tree)

    def test_invalid_types_are_controlled_input_errors(self):
        base = {"diagram_type": "block", "nodes": [{"id": "a", "label": "A"}]}
        bad_specs = [
            {**base, "diagram_type": []},
            {**base, "layout": []},
            {**base, "nodes": [{"id": "a", "label": "A", "shape": []}]},
            {**base, "nodes": [{"id": "a", "label": "A", "rounded": "false"}]},
            {**base, "edges": [{"source": "a", "target": "a", "points": [[1, 2], [1, 2]]}]},
            {**base, "edges": [{"source": "a", "target": "a", "source_port": "right", "target_port": "right", "points": [[1, 2], [3, 4]]}]},
        ]
        for spec in bad_specs:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                FIGURE.build_diagram(spec)

    def test_manual_routes_attach_after_shape_growth(self):
        spec = {"diagram_type": "flowchart", "nodes": [
            {"id": "a", "label": "条件判断输入参数" * 3, "shape": "decision", "x": 220, "y": 350},
            {"id": "b", "label": "处理", "x": 20, "y": 700}],
            "edges": [{"source": "a", "target": "b", "source_port": "left", "target_port": "top",
                       "points": [[220, 382], [150, 382], [150, 700]]}]}
        tree = svg_tree(spec)
        vertices = [tuple(map(float, p.split(","))) for p in tree.find('s:g[@data-node-id="a"]/s:polygon', NS).get("points").split()]
        path = [tuple(map(float, p.split(","))) for p in tree.find("s:polyline", NS).get("points").split()]
        self.assertEqual(path[0], vertices[3])
        self.assertEqual(path[0][1], path[1][1])
        target = tree.find('s:g[@data-node-id="b"]/s:rect', NS)
        self.assertEqual(path[-1], (float(target.get("x")) + float(target.get("width")) / 2, float(target.get("y"))))

    def test_all_automatic_routes_avoid_other_nodes(self):
        for layout, edges, ids in (("horizontal", [["a", "a"]], ["a", "b"]),
                                  ("vertical", [{"source": "a", "target": "c", "route": "bottom_return"}], ["a", "b", "c"]),
                                  ("horizontal", [["c", "a"]], ["a", "b", "c"])):
            with self.subTest(layout=layout, edges=edges):
                spec = {"diagram_type": "block", "layout": layout,
                        "nodes": [{"id": name, "label": name} for name in ids], "edges": edges}
                tree = svg_tree(spec)
                obstacles = []
                for group in tree.findall("s:g", NS):
                    if group.get("data-node-id"):
                        rect = group.find("s:rect", NS)
                        obstacles.append({"id": group.get("data-node-id"), **{key: float(rect.get(name))
                                          for key, name in [("x", "x"), ("y", "y"), ("w", "width"), ("h", "height")]}})
                path = [tuple(map(float, p.split(","))) for p in tree.find("s:polyline", NS).get("points").split()]
                self.assertFalse(FIGURE.intersects(path, obstacles, set()))

    def test_automatic_routes_honor_explicit_ports(self):
        spec = {"diagram_type": "block", "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                "edges": [{"source": "a", "target": "b", "source_port": "left", "target_port": "right"}]}
        tree = svg_tree(spec)
        points = [tuple(map(float, p.split(","))) for p in tree.find("s:polyline", NS).get("points").split()]
        for name, index, side in (("a", 0, "left"), ("b", -1, "right")):
            rect = tree.find(f's:g[@data-node-id="{name}"]/s:rect', NS)
            node = {key: float(rect.get(attr)) for key, attr in [("x", "x"), ("y", "y"), ("w", "width"), ("h", "height")]}
            self.assertEqual(points[index], FIGURE.ports(node)[side])

    def test_manual_crossings_are_rejected_including_diagonal(self):
        for points in ([[300, 72], [680, 72]], [[300, 72], [350, 20], [610, 150], [680, 72]]):
            spec = {"diagram_type": "block", "nodes": [{"id": "a", "label": "A", "x": 40, "y": 40},
                    {"id": "b", "label": "B", "x": 350, "y": 40}, {"id": "c", "label": "C", "x": 680, "y": 40}],
                    "edges": [{"source": "a", "target": "c", "points": points}]}
            with self.subTest(points=points), self.assertRaises(ValueError):
                FIGURE.build_diagram(spec)


if __name__ == "__main__":
    unittest.main()
