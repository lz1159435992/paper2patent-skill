#!/usr/bin/env python3
"""Validate evidence records and their links to patent text and diagram specs."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from claim_lint import lint_text, parse_claims, section
from patent_figure_svg import build_diagram
from record_schema import validate_record

MODES = ("full", "figures", "draft")
SECTIONS = ("说明书摘要", "摘要附图", "权利要求书", "说明书", "说明书附图")
SCHEMA = Path(__file__).resolve().parent.parent / "assets" / "evidence-map.schema.json"


def compact(text):
    return re.sub(r"\s+", "", text)


def check_evidence(data, base_dir, patent_text=None, figure_specs=None, mode="full", verify_delivery=False):
    if not isinstance(data, dict) or mode not in MODES:
        raise ValueError("evidence must be an object and mode must be full, figures or draft")
    issues = []
    checks = {name: {"status": "not_run", "reason": "未执行"} for name in
              ("record_structure", "required_inputs", "source_integrity", "source_quotes", "claims",
               "specification_anchors", "figure_correspondence", "delivered_svg")}
    quote_checked = 0
    files_checked = hashes_checked = text_hashes_checked = 0

    def add(code, message, location="", severity="error"):
        issues.append({"code": code, "severity": severity, "location": location, "message": message})

    def finish():
        errors = sum(i["severity"] == "error" for i in issues)
        warnings = sum(i["severity"] == "warning" for i in issues)
        return {"scope": "Declared mechanical checks only; semantic support is not proven; model quality is not evaluated",
                "mode": mode, "status": "draft" if mode == "draft" or errors or warnings else "ready_for_semantic_review",
                "issues": issues, "error_count": errors, "warning_count": warnings, "checks": checks,
                "delivery_status": checks["delivered_svg"]["status"]}

    schema_errors = validate_record(data, json.loads(SCHEMA.read_text(encoding="utf-8")))
    if schema_errors:
        for error in schema_errors:
            label = "locator_required" if error["path"].endswith("/locator") else "schema_violation"
            if error["path"].startswith("/effects/") and error["path"].endswith("/conditions"):
                label = "effect_conditions_required"
            add(label, error["message"], error["path"])
        checks["record_structure"] = {"status": "failed", "reason": "记录不符合本地schema"}
        return finish()
    checks["record_structure"] = {"status": "passed", "reason": "按本地schema校验字段"}
    if patent_text is not None and not isinstance(patent_text, str):
        raise ValueError("patent_text must be text")
    if figure_specs is not None and not isinstance(figure_specs, list):
        raise ValueError("figure_specs must be an array")
    declared_figures = bool(data.get("figure_edges") or data.get("artifacts")
                            or any(f.get("figure_node_ids") for f in data.get("features", []))
                            or re.search(r"图\s*\d+", patent_text or ""))
    drawing_section = section(patent_text, "说明书附图") if patent_text else None
    declared_numbers = set(re.findall(r"图\s*\d+", "\n".join(line for _, line in drawing_section or [])))
    declared_numbers = {re.sub(r"\s+", "", name) for name in declared_numbers}
    provided_numbers = {re.sub(r"\s+", "", spec["figure_no"]) for spec in figure_specs or []
                        if isinstance(spec, dict) and isinstance(spec.get("figure_no"), str)}
    input_errors = len(issues)
    if mode in {"full", "figures"} and not (patent_text and patent_text.strip()):
        add("patent_text_required", "此模式需要专利正文或说明书，不能跳过图文锚点检查")
    if (mode == "figures" or (mode == "full" and declared_figures)) and not figure_specs:
        add("figure_specs_required", "已声明附图，需要非空图规范；规划中间记录使用draft模式")
    if mode == "full" and declared_numbers - provided_numbers:
        add("figure_specs_incomplete", "说明书附图部分已声明但未提供规范：" + ", ".join(sorted(declared_numbers - provided_numbers)))
    if mode in {"full", "figures"} and not data.get("features"):
        add("empty_features", "此模式需要技术特征对应记录", "features")
    checks["required_inputs"] = {"status": "failed" if len(issues) > input_errors else "passed",
                                 "reason": "按模式及已声明内容核对输入"}

    groups = {}
    for name in ("sources", "features", "effects", "terms", "figure_edges", "unresolved"):
        value = data.get(name, [])
        if not isinstance(value, list):
            add("invalid_array", f"{name}必须是数组", name)
            value = []
        groups[name] = value
    sources, source_texts = {}, {}
    for index, source in enumerate(groups["sources"]):
        where = f"sources/{index}"
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str) or not source["source_id"]:
            add("source_id_required", "来源需要非空source_id", where)
            continue
        sid = source["source_id"]
        if sid in sources:
            add("duplicate_source_id", f"来源ID重复：{sid}", where)
            continue
        sources[sid] = source
        if source.get("kind") not in ("paper", "supplement", "original_technical", "draft", "patent_text", "background"):
            add("source_kind_required", "kind应明确为论文、补充材料、原始技术、草稿、专利正文或背景类型", where)
        has_file = bool(source.get("path"))
        has_inline = bool(source.get("inline_text"))
        if has_file and has_inline and "text_source" not in source:
            add("ambiguous_source_content", "同时提供文件和文本时需明确text_source=file或inline", where)
        selected = source.get("text_source", "file" if has_file else "inline")
        if selected == "file" and not has_file or selected == "inline" and not has_inline:
            add("text_source_missing", "text_source所选材料不存在", where)
        file_text = None
        if has_file:
            files_checked += 1
            path = Path(source["path"])
            path = path if path.is_absolute() else Path(base_dir) / path
            if not path.is_file():
                add("source_file_missing", f"来源文件不可读取：{source['path']}", where)
            else:
                raw = path.read_bytes()
                if source.get("sha256"):
                    hashes_checked += 1
                    if hashlib.sha256(raw).hexdigest().lower() != source["sha256"].lower():
                        add("source_hash_mismatch", f"来源文件已改变：{source['path']}", where)
                if path.suffix.lower() in {".txt", ".md", ".tex", ".json"}:
                    try:
                        file_text = raw.decode("utf-8-sig")
                    except UnicodeError:
                        add("source_encoding_review", "文本编码需要复核", where, "warning")
        if has_inline:
            raw_text = source["inline_text"].encode("utf-8")
            digest = source.get("text_sha256") or (source.get("sha256") if not has_file else None)
            if digest:
                text_hashes_checked += 1
                if hashlib.sha256(raw_text).hexdigest().lower() != digest.lower():
                    add("source_text_hash_mismatch", "内联文本UTF-8哈希不匹配", where)
        elif source.get("text_sha256"):
            add("text_source_missing", "text_sha256需要inline_text", where)
        text = source["inline_text"] if selected == "inline" and has_inline else file_text
        if text is not None:
            source_texts[sid] = text

    source_errors = [i for i in issues if i["location"].startswith("sources/")]
    checks["source_integrity"] = {
        "status": "failed" if source_errors else ("passed" if sources else "not_applicable"),
        "reason": "核对文件存在性及已提供的哈希；文本选择不跳过文件检查",
        "file_checked_count": files_checked, "file_hash_checked_count": hashes_checked,
        "text_hash_checked_count": text_hashes_checked}

    def evidence(item, where):
        nonlocal quote_checked
        sid = item.get("source_id")
        if not isinstance(sid, str) or sid not in sources:
            add("unknown_source", "source_id未指向已声明的来源", where)
            return
        locator = item.get("locator")
        if not isinstance(locator, (str, dict)) or not locator or (isinstance(locator, str) and not locator.strip()):
            add("locator_required", "来源定位不能为空", where)
        text = source_texts.get(sid)
        if isinstance(locator, dict) and "start_line" in locator:
            start, end = locator.get("start_line"), locator.get("end_line", locator.get("start_line"))
            if (type(start) is not int or type(end) is not int or start < 1 or end < start
                or (text is not None and end > len(text.splitlines()))):
                add("locator_range", "来源行号范围无效", where)
        quote = item.get("source_quote")
        if quote is not None:
            if not isinstance(quote, str) or not quote.strip():
                add("invalid_quote", "source_quote必须是非空文字", where)
            elif text is None:
                add("quote_not_checked", "此格式的引文需人工或文档工具回查", where, "warning")
            else:
                quote_checked += 1
                located = text
                if isinstance(locator, dict) and type(locator.get("start_line")) is int:
                    start, end = locator["start_line"], locator.get("end_line", locator["start_line"])
                    if type(end) is int and 1 <= start <= end <= len(text.splitlines()):
                        located = "\n".join(text.splitlines()[start - 1:end])
                if compact(quote) not in compact(located):
                    add("quote_not_found", "引文不在指定来源或定位范围中", where)
        if mode == "full" and sources[sid].get("kind") in ("draft", "patent_text", "background"):
            add("nonoriginal_technical_source", "完整转换不能只以草稿或背景材料支持本发明特征", where)

    figures, node_refs, edge_refs = {}, {}, set()
    for index, spec in enumerate(figure_specs or []):
        where = f"figures/{index}"
        if not isinstance(spec, dict):
            add("invalid_figure", "图规范必须是对象", where)
            continue
        figure_no = spec.get("figure_no")
        if not isinstance(figure_no, str) or not figure_no:
            add("figure_no_required", "对应检查需要显式figure_no", where)
            continue
        if figure_no in figures:
            add("duplicate_figure_no", f"图号重复：{figure_no}", where)
            continue
        figures[figure_no] = spec
        try:
            build_diagram(spec)
        except (ValueError, TypeError) as exc:
            add("invalid_figure", str(exc), where)
            continue
        for node in spec["nodes"]:
            key = f'{figure_no}:{node["id"]}'
            node_refs[key] = node
        for raw in spec.get("edges", []):
            source, target = (raw["source"], raw["target"]) if isinstance(raw, dict) else raw
            edge_refs.add((figure_no, source, target))

    def resolve_node(value, where):
        if not isinstance(value, str):
            add("invalid_node_reference", "图节点引用必须是文字", where)
            return None
        if value in node_refs:
            return value
        matches = [key for key in node_refs if key.split(":", 1)[1] == value]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            add("ambiguous_node_reference", "跨图节点重名，请使用图号:节点ID", where)
        else:
            add("unknown_node_reference", f"图节点不存在：{value}", where)
        return None

    claims = parse_claims(patent_text) if patent_text is not None else []
    claim_ids = {item["number"] for item in claims}
    if patent_text and mode == "full":
        claim_report = lint_text(patent_text, patent=mode == "full")
        for issue in claim_report["issues"]:
            add(issue["code"], issue["message"], f'claims/{issue["claim"]}', issue["severity"])
        checks["claims"] = {"status": "failed" if claim_report["error_count"] else "passed",
                            "reason": "权项结构检查", "warning_count": claim_report["warning_count"]}
    elif mode == "figures" and patent_text:
        checks["claims"] = {"status": "passed" if claims else "not_applicable",
                            "reason": "仅解析编号用于图文对应，不声称权项格式审查"}
    covered_claims, covered_nodes, feature_ids = set(), set(), set()
    if mode == "full" and not groups["features"]:
        add("empty_features", "完整转换需要记录必要技术特征", "features")
    if mode == "full":
        if patent_text is None:
            add("patent_text_required", "完整转换对应检查需要专利正文")
        else:
            for name in SECTIONS:
                content = section(patent_text, name)
                if content is None:
                    add("missing_patent_section", f"缺少{name}")
                elif not any(line.strip() for _, line in content):
                    add("empty_patent_section", f"{name}只有标题没有内容")

    specification = section(patent_text, "说明书") if patent_text is not None else None
    spec_text = "\n".join(line for _, line in specification) if specification is not None else patent_text

    def spec_locator(item, where):
        locator = item.get("specification_locator")
        anchor = locator.get("anchor") if isinstance(locator, dict) else locator
        if not isinstance(anchor, str) or not anchor.strip():
            add("specification_locator_required", "需要说明书可检索锚点", where)
        elif spec_text is not None and compact(anchor) not in compact(spec_text):
            add("specification_anchor_missing", f"说明书找不到锚点：{anchor}", where)

    for index, feature in enumerate(groups["features"]):
        where = f"features/{index}"
        if not isinstance(feature, dict):
            add("invalid_feature", "特征记录必须是对象", where)
            continue
        fid = feature.get("feature_id")
        if not isinstance(fid, str) or not fid:
            add("feature_id_required", "特征需要非空ID", where)
        elif fid in feature_ids:
            add("duplicate_feature_id", f"特征ID重复：{fid}", where)
        else:
            feature_ids.add(fid)
        if not isinstance(feature.get("description"), str) or not feature["description"].strip():
            add("feature_description_required", "需要技术描述", where)
        state = feature.get("support_status")
        if state not in ("supported", "unverified", "missing"):
            add("invalid_support_status", "支持状态应为supported、unverified或missing", where)
        elif state != "supported":
            add("support_pending", "技术来源尚未确认；交付保持草稿状态", where, "warning")
        else:
            evidence(feature, where)
        if mode == "full" or "specification_locator" in feature:
            spec_locator(feature, where)
        numbers = feature.get("claim_numbers", [])
        if not isinstance(numbers, list) or not all(type(n) is int and n > 0 for n in numbers):
            add("invalid_claim_reference", "claim_numbers应为正整数数组", where)
        else:
            for number in numbers:
                if patent_text is not None and number not in claim_ids:
                    add("unknown_claim_reference", f"权项不存在：{number}", where)
                covered_claims.add(number)
        nodes = feature.get("figure_node_ids", [])
        if not isinstance(nodes, list):
            add("invalid_node_reference", "figure_node_ids应为数组", where)
        elif figure_specs is not None:
            for value in nodes:
                key = resolve_node(value, where)
                if key:
                    covered_nodes.add(key)

    for index, effect in enumerate(groups["effects"]):
        where = f"effects/{index}"
        if not isinstance(effect, dict):
            add("invalid_effect", "效果记录必须是对象", where)
            continue
        evidence(effect, where)
        if effect.get("value") is not None and not effect.get("conditions"):
            add("effect_conditions_required", "量化效果需要测试条件", where)

    covered_edges = set()
    for index, edge in enumerate(groups["figure_edges"]):
        where = f"figure_edges/{index}"
        if not isinstance(edge, dict):
            add("invalid_edge_record", "连线记录必须是对象", where)
            continue
        key = (edge.get("figure_no"), edge.get("source_node"), edge.get("target_node"))
        if not all(isinstance(v, str) and v for v in key):
            add("invalid_edge_reference", "连线需要图号和两端节点ID", where)
        elif figure_specs is not None and key not in edge_refs:
            add("unknown_edge_reference", "图规范中不存在记录的连线", where)
        else:
            covered_edges.add(key)
        spec_locator(edge, where)

    term_numbers = {}
    for index, term in enumerate(groups["terms"]):
        if not isinstance(term, dict) or not isinstance(term.get("canonical_name"), str):
            add("invalid_term", "术语记录需要canonical_name", f"terms/{index}")
            continue
        ref = term.get("reference_number")
        if ref is not None:
            if not isinstance(ref, (str, int)) or isinstance(ref, bool):
                add("invalid_term_number", "术语标号应为文字或整数", f"terms/{index}")
                continue
            key = str(ref)
            if key in term_numbers and term_numbers[key] != term["canonical_name"]:
                add("term_number_conflict", f"标号{key}指向不同术语", f"terms/{index}")
            term_numbers[key] = term["canonical_name"]

    if mode == "full":
        for number in sorted(claim_ids - covered_claims):
            add("uncovered_claim", f"权项{number}没有特征来源记录", "features")
    if mode in {"full", "figures"} and figure_specs is not None:
        for key, node in node_refs.items():
            control = node.get("shape") == "terminator" and node["label"].strip() in {"开始", "结束", "Start", "End"}
            if key not in covered_nodes and not control:
                add("uncovered_node", f"图节点缺少对应特征：{key}", "features")
        for key in sorted(edge_refs - covered_edges):
            add("uncovered_edge", f"连线缺少说明书对应：{key}", "figure_edges")
    for index, item in enumerate(groups["unresolved"]):
        add("unresolved_item", str(item), f"unresolved/{index}", "warning")
    quote_issues = [i for i in issues if i["code"] in
                    {"quote_not_found", "quote_not_checked", "invalid_quote", "locator_range", "locator_required"}]
    checks["source_quotes"] = {"status": "failed" if quote_issues else ("passed" if quote_checked else "not_applicable"),
                                "reason": "仅比对已提供且可读取的引文", "checked_count": quote_checked}
    anchor_errors = [i for i in issues if "specification_" in i["code"]]
    checks["specification_anchors"] = {
        "status": "not_run" if not patent_text else ("failed" if anchor_errors else "passed"),
        "reason": "实际说明书锚点检查" if patent_text else "缺少正文，未执行锚点检查"}
    figure_errors = [i for i in issues if i["code"] in {
        "invalid_figure", "figure_no_required", "duplicate_figure_no", "unknown_node_reference",
        "ambiguous_node_reference", "unknown_edge_reference", "uncovered_node", "uncovered_edge"}]
    checks["figure_correspondence"] = {
        "status": ("failed" if figure_errors else "passed") if figure_specs else
                  ("not_run" if declared_figures or mode == "figures" else "not_applicable"),
        "reason": "图JSON与记录的对应检查" if figure_specs else "未提供图规范"}

    artifacts = data.get("artifacts", [])
    if verify_delivery or artifacts:
        delivery_start = len(issues)
        artifact_numbers = set()
        for index, artifact in enumerate(artifacts):
            where = f"artifacts/{index}"
            figure_no = artifact["figure_no"]
            if figure_no in artifact_numbers:
                add("duplicate_artifact", f"重复的图交付：{figure_no}", where)
            artifact_numbers.add(figure_no)
            if figure_no not in figures:
                add("artifact_spec_missing", f"{figure_no}没有对应图规范", where)
                continue
            path = Path(artifact["path"])
            path = path if path.is_absolute() else Path(base_dir) / path
            if not path.is_file():
                add("artifact_missing", f"实际SVG文件不存在：{artifact['path']}", where)
                continue
            if path.suffix.lower() != ".svg":
                add("artifact_format", "当前交付检查支持SVG", where)
                continue
            raw = path.read_bytes()
            if artifact.get("sha256") and hashlib.sha256(raw).hexdigest().lower() != artifact["sha256"].lower():
                add("artifact_hash_mismatch", "SVG文件哈希不匹配", where)
            if artifact.get("spec_sha256"):
                encoded = json.dumps(figures[figure_no], ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")
                if hashlib.sha256(encoded).hexdigest().lower() != artifact["spec_sha256"].lower():
                    add("artifact_spec_hash_mismatch", "图规范哈希不匹配", where)
            try:
                actual = ET.fromstring(raw)
                if actual.tag != "{http://www.w3.org/2000/svg}svg":
                    add("artifact_format", "文件不是标准SVG根元素", where)
                    continue
                if artifact.get("renderer", "bundled") == "external":
                    add("artifact_external_review", "外部SVG已解析，图文一致性仍需视觉复核", where, "warning")
                else:
                    expected = ET.fromstring(build_diagram(figures[figure_no]))
                    if svg_fingerprint(actual) != svg_fingerprint(expected):
                        add("artifact_svg_mismatch", "实际SVG与当前图规范生成结果不同，需重新生成或复核", where)
            except (ET.ParseError, ValueError, TypeError) as exc:
                add("artifact_invalid", f"SVG不可比对：{exc}", where)
            if patent_text:
                if re.search(r"\.svg\b", patent_text, re.IGNORECASE):
                    if path.name not in patent_text:
                        add("artifact_filename_not_referenced", f"正文显式SVG文件名未对应交付文件：{path.name}", where)
                elif figure_no not in patent_text:
                    add("artifact_figure_no_not_referenced", f"正文未引用图号：{figure_no}", where)
        for figure_no in figures.keys() - artifact_numbers:
            add("artifact_missing", f"{figure_no}缺少实际SVG交付记录", "artifacts")
        checks["delivered_svg"] = {
            "status": "failed" if len(issues) > delivery_start else "passed",
            "reason": "实际文件、正文文件名及当前图规范的SVG比对", "checked_count": len(artifacts)}
        if not artifacts and not figures:
            checks["delivered_svg"] = {"status": "not_run" if declared_figures or mode == "figures" else "not_applicable",
                                       "reason": "缺少图输入" if declared_figures or mode == "figures" else "此任务未声明附图",
                                       "checked_count": 0}
    else:
        checks["delivered_svg"] = {"status": "not_run", "reason": "规划/记录核验未开启交付检查"}
    return finish()


def svg_fingerprint(element):
    text = element.text or ""
    return (element.tag, tuple(sorted(element.attrib.items())), text if text.strip() else "",
            tuple(svg_fingerprint(child) for child in element))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--patent", type=Path)
    parser.add_argument("--figures", nargs="+", type=Path)
    parser.add_argument("--mode", choices=MODES, default="full")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--verify-delivery", action="store_true", help="require and compare declared SVG artifacts")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8-sig"))
        patent = args.patent.read_text(encoding="utf-8-sig") if args.patent else None
        figures = [json.loads(p.read_text(encoding="utf-8-sig")) for p in args.figures] if args.figures is not None else None
        report = check_evidence(data, args.evidence.resolve().parent, patent, figures, args.mode, args.verify_delivery)
    except (OSError, ValueError) as exc:
        print(f"Evidence input error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for issue in report["issues"]:
            print(f'[{issue["severity"]}:{issue["code"]}] {issue["location"]}: {issue["message"]}')
        print(f'状态{report["status"]}；错误{report["error_count"]}；待复核{report["warning_count"]}')
        for name, result in report["checks"].items():
            print(f'[check:{name}] {result["status"]}: {result["reason"]}')
        print(report["scope"])
    return int(bool(report["error_count"] or (args.strict and report["status"] == "draft")))


if __name__ == "__main__":
    raise SystemExit(main())
