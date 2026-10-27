#!/usr/bin/env python3
"""Exercise the template's "Publish GitHub Release" step against a fake gh.

The release step is the riskiest branch of the workflow: it must create a missing
release, replace assets on an existing published release, and repair a leftover
draft — without ever deleting a tag or publishing an empty release. This script
extracts that exact shell block from assets/workflow-macos-package.yml, runs it in
a temporary directory with a fake `gh` on PATH, and asserts the commands produced
by each branch. No network access, no real GitHub calls.

Usage:
    python3 scripts/mock-release-branches.py [--root PATH]

Exit code 0 when all three scenarios pass.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TEMPLATE = Path("assets/workflow-macos-package.yml")
STEP_NAME = "Publish GitHub Release"
ASSET_NAME_RE = re.compile(r"^\s+ASSET_NAME:\s*(\S+)\s*$", re.MULTILINE)

FAKE_GH = """#!/usr/bin/env bash
printf 'gh %s\\n' "$*" >> "${GH_LOG:?GH_LOG is not set}"
if [ "$1 $2" = "release view" ]; then
  if [ "${MOCK_VIEW_EXIT:-1}" = "0" ]; then
    printf '%s\\n' "${MOCK_IS_DRAFT:-false}"
    exit 0
  fi
  echo "release not found" >&2
  exit 1
fi
exit 0
"""


def extract_release_step(template_text: str) -> str:
    """Return the dedented shell body of the step named STEP_NAME."""
    lines = template_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == f"- name: {STEP_NAME}":
            start = index
            break
    if start is None:
        raise SystemExit(f"error: step {STEP_NAME!r} not found in {TEMPLATE}")

    run_line = None
    for index in range(start, len(lines)):
        if re.match(r"^\s+run:\s*\|-?\s*$", lines[index]):
            run_line = index
            break
    if run_line is None:
        raise SystemExit(f"error: no block `run:` found in step {STEP_NAME!r}")

    base_indent = len(lines[run_line]) - len(lines[run_line].lstrip(" "))
    body: list[str] = []
    for line in lines[run_line + 1 :]:
        if not line.strip():
            body.append("")
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= base_indent:
            break
        body.append(line)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        raise SystemExit(f"error: step {STEP_NAME!r} has an empty run block")
    trim = min(len(line) - len(line.lstrip(" ")) for line in body if line.strip())
    return "\n".join(line[trim:] for line in body)


def run_scenario(
    script: str, asset_name: str, view_exit: str, is_draft: str
) -> tuple[int, list[str]]:
    with tempfile.TemporaryDirectory(prefix="mock-release-") as temp:
        root = Path(temp)
        (root / "release").mkdir()
        (root / "release" / asset_name).write_text("fake installer\n", encoding="utf-8")
        (root / "release" / "SHA256SUMS.txt").write_text("fake checksum\n", encoding="utf-8")
        (root / "release" / "RELEASE_NOTES.md").write_text("fake notes\n", encoding="utf-8")
        (root / "step.sh").write_text(script + "\n", encoding="utf-8")

        bin_dir = root / "bin"
        bin_dir.mkdir()
        fake_gh = bin_dir / "gh"
        fake_gh.write_text(FAKE_GH, encoding="utf-8")
        fake_gh.chmod(0o755)

        log_path = root / "gh.log"
        env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "GH_LOG": str(log_path),
            "GH_TOKEN": "fake-token",
            "RELEASE_TAG": "v1.2.3",
            "GITHUB_REPOSITORY": "owner/repo",
            "ASSET_NAME": asset_name,
            "MOCK_VIEW_EXIT": view_exit,
            "MOCK_IS_DRAFT": is_draft,
        }
        result = subprocess.run(
            ["bash", str(root / "step.sh")],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        log = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
        return result.returncode, log


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
    template_path = root / TEMPLATE
    template_text = template_path.read_text(encoding="utf-8")

    match = ASSET_NAME_RE.search(template_text)
    if not match:
        raise SystemExit("error: cannot find ASSET_NAME in the template job env")
    asset_name = match.group(1)

    script = extract_release_step(template_text)
    failures: list[str] = []
    scenarios = [
        # label, view exit, isDraft, expected substrings, forbidden substrings
        (
            "missing release -> create",
            "1",
            "false",
            [
                f"gh release view v1.2.3",
                f"gh release create v1.2.3 release/{asset_name} release/SHA256SUMS.txt",
                "--verify-tag",
            ],
            ["gh release upload", "gh release edit"],
        ),
        (
            "published release -> re-upload",
            "0",
            "false",
            [
                f"gh release view v1.2.3",
                f"gh release upload v1.2.3 release/{asset_name} release/SHA256SUMS.txt",
                "--clobber",
            ],
            ["gh release create", "gh release edit"],
        ),
        (
            "leftover draft -> repair",
            "0",
            "true",
            [
                f"gh release view v1.2.3",
                f"gh release upload v1.2.3 release/{asset_name} release/SHA256SUMS.txt",
                "gh release edit v1.2.3 --draft=false",
            ],
            ["gh release create"],
        ),
    ]

    for label, view_exit, is_draft, expected, forbidden in scenarios:
        code, log = run_scenario(script, asset_name, view_exit, is_draft)
        joined = "\n".join(log)
        problems: list[str] = []
        if code != 0:
            problems.append(f"step exited {code}")
        for needle in expected:
            if needle not in joined:
                problems.append(f"missing command: {needle}")
        for needle in forbidden:
            if needle in joined:
                problems.append(f"unexpected command: {needle}")
        if log[:1] == [] or "--json isDraft" not in joined.splitlines()[0]:
            problems.append("branch detection did not query isDraft first")
        if problems:
            failures.extend(f"{label}: {problem}" for problem in problems)
            print(f"[fail] {label}")
        else:
            print(f"[ok]   {label}")

    print()
    if failures:
        print(f"FAILED with {len(failures)} issue(s):")
        for entry in failures:
            print(f"  - {entry}")
        return 1
    print("PASSED: release publish branches behave as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
