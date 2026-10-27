#!/usr/bin/env python3
"""Validate the github-actions-macos-release skill bundle.

Checks performed:
  1. SKILL.md frontmatter: delimiters, kebab-case name, description, whenToUse
  2. Required files exist
  3. Workflow template guardrails (permissions, version guard, --verify-tag, ...)
  4. Shell syntax of every `run:` block in bundled YAML files (`bash -n`)
  5. The macOS bash 3.2 pitfall: `$var` immediately followed by a non-ASCII byte
  6. Relative Markdown links in SKILL.md / README*.md / references/*.md resolve
  7. README files mention the skill name and the template path

Stdlib only (Python 3.8+), no network access. Exit code 0 = all checks passed.

Usage:
    python3 scripts/validate.py [--root PATH]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
LINK_RE = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
VAR_BEFORE_NON_ASCII_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")
RUN_BLOCK_RE = re.compile(r"^(?P<indent>\s*)(?:-\s+)?run:\s*\|-?\s*$")
RUN_INLINE_RE = re.compile(r"^\s*(?:-\s+)?run:\s+(?P<script>\S.*)$")

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "README.zh.md",
    "LICENSE",
    "assets/workflow-macos-package.yml",
    "references/checklist.md",
    "references/stacks.md",
    "references/environment-facts.md",
    ".github/workflows/ci.yml",
]

TEMPLATE_GUARDRAILS = [
    "permissions:",
    "contents: write",
    "concurrency:",
    "github.event.inputs.tag",
    "persist-credentials: false",
    "actions/upload-artifact@",
    "if-no-files-found: error",
    "compression-level: 0",
    "shasum -a 256",
    "ditto -x -k",
    "codesign --verify",
    "gh release create",
    "gh release upload",
    "--verify-tag",
    "--clobber",
    "ADAPT",
]

YAML_FILES = [
    "assets/workflow-macos-package.yml",
    ".github/workflows/ci.yml",
]

failures: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def ok(message: str) -> None:
    print(f"[ok]   {message}")


def warn(message: str) -> None:
    notes.append(message)
    print(f"[warn] {message}")


def parse_frontmatter(text: str) -> dict[str, str] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            continue  # nested values are not needed by the catalog
        key, separator, value = line.partition(":")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        frontmatter[key.strip()] = value
    return frontmatter


def check_skill_frontmatter(root: Path) -> None:
    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        fail("SKILL.md is missing")
        return
    frontmatter = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
    if frontmatter is None:
        fail("SKILL.md does not start with a YAML frontmatter block")
        return

    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    when_to_use = frontmatter.get("whenToUse")

    if not name:
        fail("frontmatter: `name` is required")
    elif not KEBAB_RE.match(name):
        fail(f"frontmatter: `name` is not kebab-case: {name!r}")
    else:
        ok(f"frontmatter name: {name}")
        if root.name != name:
            warn(
                f"bundle directory {root.name!r} differs from skill name {name!r}; "
                "clone/install the bundle under the skill name for clarity"
            )

    if not description:
        fail("frontmatter: `description` is required")
    elif len(description) < 20:
        fail(f"frontmatter: `description` is too short ({len(description)} chars)")
    elif len(description) > 1024:
        fail(f"frontmatter: `description` is too long ({len(description)} chars, catalog cap)")
    else:
        ok(f"frontmatter description: {len(description)} chars")

    if when_to_use is not None and not when_to_use.strip():
        fail("frontmatter: `whenToUse` is present but empty")
    elif when_to_use is not None:
        ok("frontmatter whenToUse present")


def check_required_files(root: Path) -> None:
    missing = [relative for relative in REQUIRED_FILES if not (root / relative).is_file()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")
    else:
        ok(f"required files present ({len(REQUIRED_FILES)})")


def check_template(root: Path) -> tuple[str, str] | None:
    template_path = root / "assets/workflow-macos-package.yml"
    if not template_path.is_file():
        return None
    text = template_path.read_text(encoding="utf-8")
    missing = [marker for marker in TEMPLATE_GUARDRAILS if marker not in text]
    if missing:
        fail(f"workflow template missing guardrails: {', '.join(missing)}")
    else:
        ok(f"workflow template guardrails present ({len(TEMPLATE_GUARDRAILS)})")
    adapt_count = text.count("ADAPT")
    if adapt_count < 5:
        fail(f"workflow template has only {adapt_count} ADAPT markers; expected >= 5")
    else:
        ok(f"workflow template ADAPT markers: {adapt_count}")
    return template_path.read_text(encoding="utf-8"), str(template_path)


def extract_run_scripts(text: str) -> list[tuple[int, str]]:
    """Return (line_number, script) for every `run:` block, block scalar or inline."""
    scripts: list[tuple[int, str]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        block = RUN_BLOCK_RE.match(line)
        if block:
            base_indent = len(block.group("indent"))
            body: list[str] = []
            start_line = index + 1
            cursor = index + 1
            while cursor < len(lines):
                candidate = lines[cursor]
                if candidate.strip() == "":
                    body.append("")
                    cursor += 1
                    continue
                indent = len(candidate) - len(candidate.lstrip(" "))
                if indent <= base_indent:
                    break
                body.append(candidate)
                cursor += 1
            while body and body[-1] == "":
                body.pop()
            if body:
                non_empty = [entry for entry in body if entry.strip()]
                trim = min(len(entry) - len(entry.lstrip(" ")) for entry in non_empty)
                scripts.append((start_line, "\n".join(entry[trim:] for entry in body)))
            index = cursor
            continue
        inline = RUN_INLINE_RE.match(line)
        if inline and "|" not in line:
            scripts.append((index + 1, inline.group("script").strip()))
        index += 1
    return scripts


def check_shell_syntax(root: Path) -> None:
    bash = None
    for candidate in ("bash", "/bin/bash"):
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            bash = candidate
            break
        except (OSError, subprocess.CalledProcessError):
            continue
    if bash is None:
        warn("bash not found; skipping `bash -n` syntax checks")
        return

    checked = 0
    for relative in YAML_FILES:
        path = root / relative
        if not path.is_file():
            continue
        for line_number, script in extract_run_scripts(path.read_text(encoding="utf-8")):
            result = subprocess.run(
                [bash, "-n"], input=script, capture_output=True, text=True
            )
            checked += 1
            if result.returncode != 0:
                message = (result.stderr or result.stdout).strip().splitlines()
                detail = message[0] if message else "unknown error"
                fail(f"{relative}:{line_number} shell syntax error: {detail}")
    if checked:
        ok(f"shell syntax of run blocks ({checked} scripts)")


def check_bash_unicode_pitfall(root: Path) -> None:
    """Reject `$var` immediately followed by a non-ASCII byte (bash 3.2 bug)."""
    candidates = [root / path for path in YAML_FILES]
    candidates += sorted((root / "scripts").glob("**/*.sh"))
    candidates += sorted((root / "assets").glob("**/*.sh"))
    checked = 0
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        checked += 1
        for match in VAR_BEFORE_NON_ASCII_RE.finditer(text):
            following = text[match.end() : match.end() + 1]
            if following and ord(following) > 127:
                line = text.count("\n", 0, match.start()) + 1
                fail(
                    f"{path.relative_to(root)}:{line} `{match.group()}` is followed by a "
                    "non-ASCII byte; use ${var} (macOS bash 3.2 merges it into the name)"
                )
    if checked:
        ok(f"bash 3.2 variable/Unicode pitfall ({checked} files)")


def check_markdown_links(root: Path) -> None:
    markdown_files = [
        root / "SKILL.md",
        root / "README.md",
        root / "README.zh.md",
    ] + sorted((root / "references").glob("*.md"))
    broken: list[str] = []
    checked = 0
    for path in markdown_files:
        if not path.is_file():
            continue
        in_fence = False
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for match in LINK_RE.finditer(line):
                target = match.group(1)
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target = target.split("#", 1)[0]
                if not target or "*" in target or "<" in target:
                    continue
                if not any(ch.isalnum() or ch in "-_./" for ch in target):
                    continue
                resolved = (path.parent / target).resolve()
                checked += 1
                if not resolved.exists():
                    broken.append(f"{path.relative_to(root)}:{line_number} -> {target}")
    if broken:
        fail("broken relative Markdown links:\n  " + "\n  ".join(broken))
    elif checked:
        ok(f"relative Markdown links ({checked} links)")


def check_readme_content(root: Path) -> None:
    readme = root / "README.md"
    readme_zh = root / "README.zh.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        for marker, label in (
            ("github-actions-macos-release", "skill name"),
            ("assets/workflow-macos-package.yml", "template path"),
            ("~/.dsh/skills", "DSH install path"),
        ):
            if marker not in text:
                fail(f"README.md does not mention the {label}")
        if "MIT" not in text:
            fail("README.md does not mention the license")
        if not any(marker in text.lower() for marker in ("## install", "## usage", "## quick start")):
            fail("README.md has no install/usage section heading")
        ok("README.md content markers")
    if readme_zh.is_file() and not readme_zh.read_text(encoding="utf-8").strip():
        fail("README.zh.md is empty")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="skill bundle root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    print(f"Validating skill bundle: {root}\n")

    check_skill_frontmatter(root)
    check_required_files(root)
    check_template(root)
    check_shell_syntax(root)
    check_bash_unicode_pitfall(root)
    check_markdown_links(root)
    check_readme_content(root)

    print()
    if failures:
        print(f"FAILED with {len(failures)} issue(s):")
        for entry in failures:
            print(f"  - {entry}")
        return 1
    if notes:
        print(f"PASSED with {len(notes)} warning(s)")
    else:
        print("PASSED: skill bundle is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
