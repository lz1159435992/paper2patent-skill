#!/usr/bin/env python3
"""Check the source-only distribution and its attributed fixture integrity."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "paper2patent"
ROOT_FILES = {"README.md", "LICENSE", "NOTICE.md", "VERSION", "CHANGELOG.md",
              "CONTRIBUTING.md", "requirements-png.txt", ".gitignore", ".gitattributes"}
EXTENSIONS = {".md", ".txt", ".py", ".json", ".svg", ".yaml", ".yml"}
PROMPT_HASHES = {
    "flash-prompt.md": "d05ea58a8b4b81a17084581ac1bf6735e898decf4ab27558a88277d5fc00b67a",
    "pro-prompt.md": "c0ab006578adf9096ed92c8f7ec16d49711721d7cc646d2152c2517ffdb1609d",
    "gemini-figure-prompt.md": "f45c749629c1b880898faae5523d5ebc77c9620b62a3bda849d76cf99a148dfc",
}


def candidate_files() -> list[Path]:
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                check=True, capture_output=True)
        return [ROOT / name for name in result.stdout.decode("utf-8").split("\0") if name]
    return [path for path in ROOT.rglob("*") if path.is_file()
            and not {"__pycache__", "build", "dist", ".venv"}.intersection(path.relative_to(ROOT).parts)]


def main() -> int:
    failures: list[str] = []
    files = candidate_files()
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        allowed = (rel in ROOT_FILES or rel == ".github/workflows/ci.yml"
                   or rel == "tools/check_release.py" or rel.startswith("skills/paper2patent/"))
        if not allowed or (path.suffix not in EXTENSIONS and rel not in ROOT_FILES and path.name != "LICENSE"):
            failures.append(f"Unexpected distribution file: {rel}")
        if path.is_symlink() or "__pycache__" in path.parts or not path.is_file():
            failures.append(f"Non-source or missing file: {rel}")
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except UnicodeError:
            failures.append(f"Non-UTF-8 file: {rel}")
            continue
        if "COM" + "PASS" in body or "Leno" + "vo" in body:
            failures.append(f"Private evaluation marker: {rel}")
        if re.search(r"[A-Za-z]:[\\/](?:Users|git_paper)[\\/]", body):
            failures.append(f"Personal absolute path: {rel}")
        if re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", body):
            failures.append(f"Credential-shaped content: {rel}")
        if path.suffix == ".md":
            prose = re.sub(r"^```.*?^```[^\n]*$", "", body, flags=re.M | re.S)
            for target in re.findall(r"\]\(([^)\s]+)\)", prose):
                if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                    continue
                destination = target.split("#", 1)[0]
                if destination and not (path.parent / destination).exists():
                    failures.append(f"Broken local link in {rel}: {target}")

    entry = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if not re.match(r"\A---\nname: paper2patent\ndescription: .+\n---\n", entry):
        failures.append("Invalid skill entry frontmatter")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?", version):
        failures.append("Invalid release version")
    for name, digest in PROMPT_HASHES.items():
        archive = (SKILL / "references" / name).read_text(encoding="utf-8")
        start = archive.index("```markdown\n") + len("```markdown\n")
        end = archive.rfind("\n```")
        actual = hashlib.sha256(archive[start:end].encode("utf-8")).hexdigest()
        if actual != digest:
            failures.append(f"Archived prompt body changed: {name}")

    upstream = (SKILL / "references" / "upstream-license.txt").read_bytes()
    git_blob = b"blob " + str(len(upstream)).encode("ascii") + b"\0" + upstream
    if hashlib.sha1(git_blob).hexdigest() != "9dfb886a6af7be9885bc489b5256e6bd5afafcce":
        failures.append("Upstream license differs from the verified original")
    if (ROOT / "LICENSE").read_bytes() != (SKILL / "LICENSE").read_bytes():
        failures.append("Repository and installable skill licenses differ")

    fixtures = SKILL / "tests" / "fixtures"
    source_hash = hashlib.sha256((fixtures / "synthetic-source.txt").read_bytes()).hexdigest()
    provenance = json.loads((fixtures / "synthetic-provenance.json").read_text(encoding="utf-8"))
    evidence = json.loads((fixtures / "synthetic-evidence.json").read_text(encoding="utf-8"))
    if provenance.get("material_type") != "synthetic_technical_disclosure" or provenance.get("license") != "MIT":
        failures.append("Fixture provenance must state its synthetic nature and license")
    if provenance.get("contains_real_paper_or_experiment") is not False:
        failures.append("Public fixture must not contain a real paper or experiment")
    if provenance.get("origin_sha256") != source_hash or evidence["sources"][0].get("sha256") != source_hash:
        failures.append("Synthetic source hash mismatch")
    expected_fixtures = {"synthetic-source.txt", "synthetic-patent-draft.txt", "synthetic-figure1.json",
                         "synthetic-figure1.svg", "synthetic-evidence.json", "synthetic-provenance.json"}
    if {path.name for path in fixtures.iterdir()} != expected_fixtures:
        failures.append("Unexpected or missing public fixture")

    if failures:
        print("\n".join(failures))
        return 1
    print(f"Release {version}: {len(files)} source files checked; attribution, archives and synthetic fixtures verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
