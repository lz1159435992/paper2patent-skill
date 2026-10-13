#!/usr/bin/env python3
"""Check claim structure and report wording that needs contextual review."""
from __future__ import annotations
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "references" / "claim-rules.json"
NUMBERED = re.compile(r"^\s*(\d+)\s*([.．、。])\s*(?=[^\d\s]|$)")
REFERENCE = re.compile(r"权利要求(?!书)")


def heading(line: str) -> str:
    line = re.sub(r"^[一二三四五六七八九十\d]+[、.．]\s*", "", line.strip().strip("#* ").strip())
    return line.rstrip(":：")


def section(text: str, name: str) -> list[tuple[int, str]] | None:
    lines = text.lstrip("\ufeff").splitlines()
    start = next((i for i, line in enumerate(lines) if heading(line) == name), None)
    if start is None:
        return None
    result = []
    for index in range(start + 1, len(lines)):
        if heading(lines[index]) in {"说明书摘要", "摘要附图", "权利要求书", "说明书", "说明书附图"}:
            break
        result.append((index + 1, lines[index]))
    return result


def parse_claims(text: str) -> list[dict]:
    lines = section(text, "权利要求书")
    if lines is None:
        lines = list(enumerate(text.lstrip("\ufeff").splitlines(), 1))
    claims = []
    current = None
    for line_number, raw in lines:
        line = raw.strip()
        if not line or line.startswith(chr(96) * 3):
            continue
        match = NUMBERED.match(line)
        if match:
            if current is not None:
                claims.append(current)
            current = {"number": int(match[1]), "marker": match[2], "line": line_number, "body": line[match.end():]}
        elif current is not None:
            current["body"] += "\n" + line
    if current is not None:
        claims.append(current)
    return claims


def extract_claims(text: str) -> list[str]:
    return [f'{item["number"]}.{item["body"]}' for item in parse_claims(text)]


def load_rules(path: Path = DEFAULT_RULES) -> dict:
    rules = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rules, dict):
        raise ValueError("rules must be an object")
    for key in ("review_terms", "technical_compounds", "manual_checks"):
        if not isinstance(rules.get(key), list) or not all(isinstance(v, str) and v for v in rules[key]):
            raise ValueError(f"rules.{key} must be an array of nonempty strings")
    return rules


def references(body: str, count: int) -> tuple[list[int], bool, str | None]:
    refs, alternatives = set(), []
    consumed = 0
    for marker in REFERENCE.finditer(body):
        if marker.start() < consumed:
            continue
        tail = body[marker.end():]
        end = re.search(r"所述|所记载|记载|限定", tail)
        if end is None:
            return sorted(refs), False, "解析不完整：引用缺少可识别的结束标记"
        consumed = marker.end() + end.end()
        expression = unicodedata.normalize("NFKC", tail[:end.start()]).strip()
        expression = expression.replace("【", "[").replace("】", "]")
        stack, stripped = [], []
        pairs = {")": "(", "]": "["}
        for char in expression:
            if char in "([":
                stack.append(char)
            elif char in pairs:
                if not stack or stack.pop() != pairs[char]:
                    return sorted(refs), False, f"解析不完整：引用括号不匹配：{expression}"
            else:
                stripped.append(char)
        if stack:
            return sorted(refs), False, f"解析不完整：引用括号未闭合：{expression}"
        expression = "".join(stripped).replace("权利要求", "")
        if re.search(r"\d\s+\d", expression):
            return sorted(refs), False, f"解析不完整：编号间缺少连接符：{expression}"
        expression = re.sub(r"\s+", "", expression)
        expression = re.sub(r"第(\d+)项", r"\1", expression)
        alternative = "或" in expression or bool(re.search(r"任意一|任一|任何一|之一", expression))
        expression = re.sub(r"(?:中)?(?:(?:任意|任|任何)一项?|之一)$", "", expression)
        parts = re.split(r"或者|或|以及|和|及|、|,", expression)
        clause_refs = set()
        for part in parts:
            interval = re.fullmatch(r"(\d+)(?:至|到|[-—~～])(\d+)", part)
            if interval:
                lower, upper = map(int, interval.groups())
                if lower > upper or upper - lower >= max(count, 1):
                    return sorted(refs), False, f"无效或超出权项数量的引用范围：{expression}"
                clause_refs.update(range(lower, upper + 1))
            elif re.fullmatch(r"\d+", part):
                clause_refs.add(int(part))
            else:
                return sorted(refs | clause_refs), False, f"解析不完整：无法识别完整引用：{expression}"
        refs.update(clause_refs)
        alternatives.append(alternative)
    return sorted(refs), bool(alternatives) and all(alternatives), None


def term_positions(body: str, term: str, compounds: list[str]):
    protected = []
    for compound in compounds:
        if term in compound:
            protected.extend((m.start(), m.end()) for m in re.finditer(re.escape(compound), body))
    for match in re.finditer(re.escape(term), body):
        if not any(a <= match.start() and match.end() <= b for a, b in protected):
            yield match.start()


def lint_text(text: str, rules: dict | None = None, patent: bool = False) -> dict:
    rules = rules if rules is not None else load_rules()
    claims = parse_claims(text)
    issues = []

    def add(code, message, claim=None, severity="error"):
        issues.append({"code": code, "severity": severity, "claim": claim["number"] if claim else None,
                       "line": claim["line"] if claim else None, "message": message})

    if not claims:
        add("no_claims", "未识别到权项；请提供独立权项文本或权利要求书部分")
    positions = {}
    deps = {}
    for index, claim in enumerate(claims):
        number, body = claim["number"], claim["body"].rstrip()
        if number in positions:
            add("duplicate_number", f"权项编号{number}重复", claim)
        else:
            positions[number] = index
        if number != index + 1:
            add("numbering_order", f"此位置应编号{index + 1}，实际为{number}", claim)
        if claim["marker"] != ".":
            add("numbering_format", "项目输出编号使用英文点，如1.正文", claim, "warning")
        if body.count("。") != 1 or not body.endswith("。"):
            add("full_stop", "每项应在末尾且仅在末尾使用一个中文句号", claim)
        if not body:
            add("empty_claim", "权项正文为空", claim)
        for term in rules["review_terms"]:
            if next(term_positions(body, term, rules["technical_compounds"]), None) is not None:
                add("wording_review", f"待结合上下文复核措辞：{term}", claim, "warning")
        refs, alternative, problem = references(body, len(claims))
        deps[index] = refs
        if problem:
            code = "reference_parse_incomplete" if problem.startswith("解析不完整") else "reference_range"
            add(code, problem, claim)
        if len(refs) > 1 and not alternative:
            add("multiple_reference_not_alternative", "多项从属引用需明确择一方式", claim)

    multiple = {claims[i]["number"] for i, refs in deps.items() if len(refs) > 1}
    for index, claim in enumerate(claims):
        for ref in deps[index]:
            if ref not in positions:
                add("unknown_reference", f"引用的权利要求{ref}不存在", claim)
            elif positions[ref] >= index:
                add("nonprior_reference", f"权利要求{ref}不是在前项", claim)
            if len(deps[index]) > 1 and ref in multiple:
                add("multiple_on_multiple", f"多项从属项不能以多项从属权利要求{ref}为基础", claim)

    abstract_count = None
    if patent:
        abstract = section(text, "说明书摘要")
        if abstract is None or not any(line.strip() for _, line in abstract):
            add("missing_abstract", "完整正文检查未找到说明书摘要")
        else:
            abstract_count = len(re.sub(r"\s+", "", "".join(line for _, line in abstract)))
            if abstract_count > 300:
                add("abstract_length", f"摘要含标点字符预检为{abstract_count}，超过300；混排需核对实际字数")
    return {
        "scope": rules.get("scope", "Mechanical checks only"),
        "claims": [{"number": c["number"], "line": c["line"], "references": deps[i]} for i, c in enumerate(claims)],
        "issues": issues,
        "error_count": sum(i["severity"] == "error" for i in issues),
        "warning_count": sum(i["severity"] == "warning" for i in issues),
        "abstract_character_count": abstract_count,
        "manual_checks_not_performed": rules["manual_checks"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--json", action="store_true", help="print a structured report")
    parser.add_argument("--strict", action="store_true", help="fail on review warnings too")
    parser.add_argument("--patent", action="store_true", help="also precheck the abstract")
    args = parser.parse_args(argv)
    try:
        report = lint_text(args.input.read_text(encoding="utf-8-sig"), load_rules(args.rules), args.patent)
    except (OSError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for issue in report["issues"]:
            where = f'权项{issue["claim"]}' if issue["claim"] is not None else "文件"
            print(f'[{issue["severity"]}:{issue["code"]}] {where}: {issue["message"]}')
        print(f'检查{len(report["claims"])}项，错误{report["error_count"]}，待复核{report["warning_count"]}')
        print("仅机械检查；来源支持、引用基础与法律判断需要另行核验。")
    return int(bool(report["error_count"] or (args.strict and report["warning_count"])))


if __name__ == "__main__":
    raise SystemExit(main())
