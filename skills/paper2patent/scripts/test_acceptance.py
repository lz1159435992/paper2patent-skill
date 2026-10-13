#!/usr/bin/env python3
"""Integration acceptance on a public synthetic disclosure and fault cases."""
from __future__ import annotations
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from claim_lint import lint_text
from evidence_check import check_evidence
from patent_figure_svg import build_diagram

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads((FIXTURES / "synthetic-evidence.json").read_text(encoding="utf-8"))
        self.patent = (FIXTURES / "synthetic-patent-draft.txt").read_text(encoding="utf-8")
        self.figure = json.loads((FIXTURES / "synthetic-figure1.json").read_text(encoding="utf-8"))

    def check(self, evidence=None, patent=None, figures=None, mode="full"):
        return check_evidence(evidence if evidence is not None else self.evidence, FIXTURES,
                              patent if patent is not None else self.patent,
                              figures if figures is not None else [self.figure], mode)

    def codes(self, **kwargs):
        return {item["code"] for item in self.check(**kwargs)["issues"]}

    def test_synthetic_bundle_pipeline(self):
        self.assertEqual(lint_text(self.patent, patent=True)["error_count"], 0)
        checked = self.check()
        self.assertEqual(checked["issues"], [], checked)
        self.assertEqual(checked["status"], "ready_for_semantic_review")
        self.assertIn("semantic support is not proven", checked["scope"])
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "synthetic-figure1.svg"
            result = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts" / "patent_figure_svg.py"),
                 str(FIXTURES / "synthetic-figure1.json"), str(out)],
                cwd=temp, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            tree = ET.parse(out)
            ns = {"s": "http://www.w3.org/2000/svg"}
            self.assertEqual(len(tree.findall(".//s:polyline", ns)), len(self.figure["edges"]))
            self.assertEqual(len(tree.findall('.//s:g[@data-node-id]', ns)), len(self.figure["nodes"]))

    def test_empty_and_nonobject_records(self):
        self.assertIn("empty_features", self.codes(evidence={"sources": [], "features": []}))
        with self.assertRaises(ValueError):
            check_evidence([], FIXTURES)

    def test_duplicate_feature_and_source_ids(self):
        data = copy.deepcopy(self.evidence)
        data["features"].append(copy.deepcopy(data["features"][0]))
        data["sources"].append(copy.deepcopy(data["sources"][0]))
        codes = self.codes(evidence=data)
        self.assertIn("duplicate_feature_id", codes)
        self.assertIn("duplicate_source_id", codes)

    def test_unknown_source_and_empty_location(self):
        data = copy.deepcopy(self.evidence)
        data["features"][0]["source_id"] = "missing"
        self.assertIn("unknown_source", self.codes(evidence=data))
        data = copy.deepcopy(self.evidence)
        data["features"][1]["locator"] = " "
        self.assertIn("locator_required", self.codes(evidence=data))

    def test_quote_and_range_are_checked_in_source(self):
        data = copy.deepcopy(self.evidence)
        data["features"][0]["source_quote"] = "This sentence is deliberately absent."
        self.assertIn("quote_not_found", self.codes(evidence=data))
        data["features"][0]["locator"] = {"start_line": 100000, "end_line": 100001}
        self.assertIn("locator_range", self.codes(evidence=data))

    def test_file_and_hash_mismatch(self):
        data = copy.deepcopy(self.evidence)
        data["sources"][0]["path"] = "not-existing.txt"
        self.assertIn("source_file_missing", self.codes(evidence=data))
        data["sources"][0]["path"] = self.evidence["sources"][0]["path"]
        data["sources"][0]["sha256"] = "0" * 64
        self.assertIn("source_hash_mismatch", self.codes(evidence=data))

    def test_draft_is_not_original_evidence_in_full_mode(self):
        data = copy.deepcopy(self.evidence)
        data["sources"][0]["kind"] = "draft"
        self.assertIn("nonoriginal_technical_source", self.codes(evidence=data))
        self.assertNotIn("nonoriginal_technical_source", self.codes(evidence=data, mode="figures"))

    def test_unknown_claim_and_specification_anchor(self):
        data = copy.deepcopy(self.evidence)
        data["features"][0]["claim_numbers"] = [99]
        data["features"][0]["specification_locator"] = {"anchor": "missing anchor"}
        codes = self.codes(evidence=data)
        self.assertIn("unknown_claim_reference", codes)
        self.assertIn("specification_anchor_missing", codes)

    def test_cross_figure_names_require_qualification(self):
        second = copy.deepcopy(self.figure)
        second["figure_no"] = "图2"
        data = copy.deepcopy(self.evidence)
        data["features"][0]["figure_node_ids"] = ["s101"]
        self.assertIn("ambiguous_node_reference", self.codes(evidence=data, figures=[self.figure, second]))

    def test_unknown_nodes_and_edges(self):
        data = copy.deepcopy(self.evidence)
        data["features"][0]["figure_node_ids"] = ["图1:missing"]
        data["figure_edges"][0]["target_node"] = "missing"
        codes = self.codes(evidence=data)
        self.assertIn("unknown_node_reference", codes)
        self.assertIn("unknown_edge_reference", codes)

    def test_coverage_gaps(self):
        data = copy.deepcopy(self.evidence)
        for feature in data["features"]:
            feature["claim_numbers"] = []
            feature["figure_node_ids"] = []
        data["figure_edges"] = []
        codes = self.codes(evidence=data)
        self.assertTrue({"uncovered_claim", "uncovered_node", "uncovered_edge"} <= codes)

    def test_incomplete_material_remains_draft(self):
        data = {"sources": [], "features": [{"feature_id": "F1", "description": "未提供方法的待核验特征",
                "support_status": "missing", "claim_numbers": [], "figure_node_ids": []}],
                "unresolved": ["缺少完整方法章节"]}
        result = check_evidence(data, FIXTURES, mode="draft")
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["status"], "draft")
        self.assertGreater(result["warning_count"], 0)

    def test_claim_only_needs_no_evidence_or_paper(self):
        self.assertEqual(lint_text("1.一种处理方法，其特征在于，获取输入并输出处理结果。")["error_count"], 0)

    def test_figure_only_requires_no_paper_backtrace(self):
        data = copy.deepcopy(self.evidence)
        data["sources"] = [{"source_id": "P1", "kind": "patent_text", "inline_text": self.patent}]
        for feature in data["features"]:
            feature["source_quote"] = feature["specification_locator"]["anchor"]
            feature["locator"] = "已有说明书"
        for effect in data["effects"]:
            effect["source_quote"] = "窗口均值达到阈值"
            effect["locator"] = "发明内容"
        result = self.check(evidence=data, mode="figures")
        self.assertEqual(result["error_count"], 0, result)
        ET.fromstring(build_diagram(self.figure))

    def test_quantitative_effect_needs_conditions(self):
        data = copy.deepcopy(self.evidence)
        data["effects"][0]["value"] = 10
        data["effects"][0]["conditions"] = ""
        self.assertIn("effect_conditions_required", self.codes(evidence=data))

    def test_missing_section_and_term_conflict(self):
        data = copy.deepcopy(self.evidence)
        data["terms"].append({"canonical_name": "另一个模块", "reference_number": "S101"})
        codes = self.codes(evidence=data, patent=self.patent.replace("五、说明书附图", "附图"))
        self.assertIn("term_number_conflict", codes)
        self.assertIn("missing_patent_section", codes)

    def test_cli_relative_paths_and_partial_status(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            for path in FIXTURES.iterdir():
                if path.is_file():
                    shutil.copy2(path, workspace / path.name)
            cmd = [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts" / "evidence_check.py"),
                   str(workspace / "synthetic-evidence.json"), "--patent", str(workspace / "synthetic-patent-draft.txt"),
                   "--figures", str(workspace / "synthetic-figure1.json"), "--json", "--strict"]
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "ready_for_semantic_review")
            data = copy.deepcopy(self.evidence)
            data["unresolved"] = ["仍需复核"]
            (workspace / "synthetic-evidence.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "draft")


    def test_required_inputs_cannot_report_ready(self):
        cases = [
            check_evidence(self.evidence, FIXTURES, self.patent, None, "full"),
            check_evidence(self.evidence, FIXTURES, None, [self.figure], "figures"),
            check_evidence({"sources": [], "features": []}, FIXTURES, mode="figures"),
        ]
        for report in cases:
            with self.subTest(report=report):
                self.assertEqual(report["status"], "draft")
                self.assertGreater(report["error_count"], 0)
                self.assertNotEqual(report["checks"]["required_inputs"]["status"], "passed")

    def test_graph_validation_not_silently_skipped(self):
        data = copy.deepcopy(self.evidence)
        data["features"][0]["figure_node_ids"] = ["图99:missing"]
        report = check_evidence(data, FIXTURES, self.patent, None)
        self.assertEqual(report["checks"]["figure_correspondence"]["status"], "not_run")
        self.assertEqual(report["status"], "draft")
        self.assertIn("figure_specs_required", {i["code"] for i in report["issues"]})

    def test_bad_types_and_meaningless_locations_are_structured(self):
        changes = [
            lambda d: d["sources"][0].update(kind=[]),
            lambda d: d["effects"][0].pop("description"),
            lambda d: d["features"][0].update(locator={"invented_field": True}),
            lambda d: d["terms"][0].update(reference_number=True),
        ]
        for change in changes:
            data = copy.deepcopy(self.evidence)
            change(data)
            with self.subTest(data=data):
                report = self.check(evidence=data)
                self.assertEqual(report["status"], "draft")
                self.assertGreater(report["error_count"], 0)
                self.assertEqual(report["checks"]["record_structure"]["status"], "failed")

    def test_dual_source_requires_selection_and_checks_file(self):
        data = copy.deepcopy(self.evidence)
        text = (FIXTURES / "synthetic-source.txt").read_text(encoding="utf-8")
        data["sources"][0].update(inline_text=text)
        self.assertIn("ambiguous_source_content", self.codes(evidence=data))
        data["sources"][0].update(text_source="inline", path="missing.txt")
        self.assertIn("source_file_missing", self.codes(evidence=data))
        data["sources"][0].update(path="synthetic-source.txt", sha256="0" * 64)
        self.assertIn("source_hash_mismatch", self.codes(evidence=data))

    def test_inline_hash_and_snapshot_hash(self):
        import hashlib
        data = copy.deepcopy(self.evidence)
        text = (FIXTURES / "synthetic-source.txt").read_text(encoding="utf-8")
        data["sources"][0] = {"source_id": "P1", "kind": "paper", "inline_text": text, "sha256": "0" * 64}
        self.assertIn("source_text_hash_mismatch", self.codes(evidence=data))
        data["sources"][0]["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.assertEqual(self.check(evidence=data)["error_count"], 0)
        data["sources"][0].update(path="synthetic-source.txt", text_source="inline", text_sha256="0" * 64)
        data["sources"][0]["sha256"] = self.evidence["sources"][0]["sha256"]
        self.assertIn("source_text_hash_mismatch", self.codes(evidence=data))

    def test_planning_and_delivery_have_separate_results(self):
        planned = self.check()
        self.assertEqual(planned["status"], "ready_for_semantic_review")
        self.assertEqual(planned["delivery_status"], "not_run")
        data = copy.deepcopy(self.evidence)
        data["artifacts"] = [{"figure_no": "图1", "path": "synthetic-figure1.svg"}]
        delivered = check_evidence(data, FIXTURES, self.patent, [self.figure], verify_delivery=True)
        self.assertEqual(delivered["issues"], [], delivered)
        self.assertEqual(delivered["delivery_status"], "passed")
        missing = check_evidence(self.evidence, FIXTURES, self.patent, [self.figure], verify_delivery=True)
        self.assertEqual(missing["status"], "draft")
        self.assertIn("artifact_missing", {i["code"] for i in missing["issues"]})

    def test_missing_stale_and_unreferenced_svg(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            shutil.copy2(FIXTURES / "synthetic-source.txt", workspace / "synthetic-source.txt")
            data = copy.deepcopy(self.evidence)
            data["artifacts"] = [{"figure_no": "图1", "path": "synthetic-figure1.svg"}]
            missing = check_evidence(data, workspace, self.patent, [self.figure], verify_delivery=True)
            self.assertIn("artifact_missing", {i["code"] for i in missing["issues"]})
            stale = copy.deepcopy(self.figure)
            stale["nodes"][0]["label"] = "旧版本节点"
            (workspace / "synthetic-figure1.svg").write_text(build_diagram(stale), encoding="utf-8")
            report = check_evidence(data, workspace, self.patent, [self.figure], verify_delivery=True)
            self.assertIn("artifact_svg_mismatch", {i["code"] for i in report["issues"]})
            (workspace / "synthetic-figure1.svg").write_text(build_diagram(self.figure), encoding="utf-8")
            report = check_evidence(data, workspace, self.patent.replace("synthetic-figure1.svg", "wrong.svg"),
                                    [self.figure], verify_delivery=True)
            self.assertIn("artifact_filename_not_referenced", {i["code"] for i in report["issues"]})

    def test_invalid_svg_and_external_renderer_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            shutil.copy2(FIXTURES / "synthetic-source.txt", workspace / "synthetic-source.txt")
            data = copy.deepcopy(self.evidence)
            data["artifacts"] = [{"figure_no": "图1", "path": "synthetic-figure1.svg"}]
            out = workspace / "synthetic-figure1.svg"
            out.write_text("not XML", encoding="utf-8")
            report = check_evidence(data, workspace, self.patent, [self.figure], verify_delivery=True)
            self.assertIn("artifact_invalid", {i["code"] for i in report["issues"]})
            out.write_text(build_diagram(self.figure), encoding="utf-8")
            data["artifacts"][0]["renderer"] = "external"
            report = check_evidence(data, workspace, self.patent, [self.figure], verify_delivery=True)
            self.assertIn("artifact_external_review", {i["code"] for i in report["issues"]})
            self.assertEqual(report["status"], "draft")

    def test_empty_patent_sections_and_bad_claims(self):
        text = self.patent.replace("2.根据权利要求1", "2.根据权利要求99")
        self.assertIn("unknown_reference", self.codes(patent=text))
        text = self.patent.replace("二、摘要附图\n（注：建议选取说明书附图中的图1作为摘要附图）",
                                  "二、摘要附图\n")
        self.assertIn("empty_patent_section", self.codes(patent=text))

    def test_formal_patent_can_reference_only_figure_numbers(self):
        data = copy.deepcopy(self.evidence)
        data["artifacts"] = [{"figure_no": "图1", "path": "synthetic-figure1.svg"}]
        text = self.patent.replace("synthetic-figure1.svg", "图1")
        report = check_evidence(data, FIXTURES, text, [self.figure], verify_delivery=True)
        self.assertEqual(report["error_count"], 0, report)
        self.assertEqual(report["delivery_status"], "passed")

    def test_unsupported_schema_constraint_is_not_ignored(self):
        from record_schema import validate_record
        with self.assertRaises(ValueError):
            validate_record("a", {"type": "string", "maxLength": 0})

    def test_full_mode_requires_all_declared_drawing_specs(self):
        text = self.patent + "\n图2为另一幅附图。\n"
        report = check_evidence(self.evidence, FIXTURES, text, [self.figure], "full")
        self.assertEqual(report["status"], "draft")
        self.assertIn("figure_specs_incomplete", {i["code"] for i in report["issues"]})
        selected = check_evidence(self.evidence, FIXTURES, text, [self.figure], "figures")
        self.assertNotIn("figure_specs_incomplete", {i["code"] for i in selected["issues"]})

    def test_draft_mode_never_presents_itself_as_completed(self):
        report = check_evidence(self.evidence, FIXTURES, self.patent, [self.figure], "draft")
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["status"], "draft")

    def test_integrity_counts_do_not_imply_an_unprovided_hash(self):
        data = copy.deepcopy(self.evidence)
        data["sources"][0].pop("sha256")
        report = self.check(evidence=data)
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["checks"]["source_integrity"]["file_checked_count"], 1)
        self.assertEqual(report["checks"]["source_integrity"]["file_hash_checked_count"], 0)

if __name__ == "__main__":
    unittest.main()
