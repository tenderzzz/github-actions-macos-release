# github-actions-macos-release

> An agent skill + drop-in workflow template for building and publishing macOS desktop-app installers with GitHub Actions.

[![CI](https://github.com/tenderzzz/github-actions-macos-release/actions/workflows/ci.yml/badge.svg)](https://github.com/tenderzzz/github-actions-macos-release/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**English** | [中文](README.zh.md)

The pipeline was verified on a real project, and this repository packages it in two reusable forms:

1. **A [DeepSeek Harness](https://github.com/deepseek-ai) (DSH) skill** — an instruction bundle that coding agents load before touching a macOS release workflow. It contains the recon checklist, design decisions, validation protocol, known pitfalls, and this template.
2. **A standalone workflow template** — `assets/workflow-macos-package.yml` can be copied into any repo's `.github/workflows/` even if you never use DSH.

On a real Electron 45 app, a manual GitHub Actions run on a macOS 26 arm64 runner passed 80/80 tests, built the installer, verified its signature, and uploaded a 125 MB artifact in ~71 s. The same workflow is wired for tag-triggered publishing; its `gh release` publish branch has been exercised locally with a mocked `gh` and awaits its first real tag release. No Apple Developer certificate or repository secret is required — builds are ad-hoc signed, and users may need right-click → Open on first launch.

## Why use it

- **Tag-triggered, safe by default.** Pushing `v*` builds, tests and publishes; a manual run builds only, and touches a Release only when you fill in a tag. A version guard fails in seconds when tag and `package.json` disagree.
- **Honest uploads.** The workflow unzips the produced archive and verifies its signature before uploading, so a broken `.app` never reaches users.
- **No secrets.** `permissions: contents: write` is enough; no PAT, certificate or notarization account for the ad-hoc tier.
- **Idempotent retries.** Draft → upload → publish semantics and draft-aware re-uploads make failed releases repairable without deleting tags.

## Install as a DSH skill

DSH discovers skills from `~/.dsh/skills/<name>/SKILL.md` (and project-level `.dsh/skills/`). Clone this repository directly into the user skills root:

```sh
git clone https://github.com/tenderzzz/github-actions-macos-release.git \
  ~/.dsh/skills/github-actions-macos-release
```

No restart is needed: adding a skill refreshes the catalog for the next model step. The agent loads it automatically when a task matches, or you can name it explicitly: *"use the `github-actions-macos-release` skill"*. Update later with `git -C ~/.dsh/skills/github-actions-macos-release pull`.

To install it for a single repository instead, clone to `<repo>/.dsh/skills/github-actions-macos-release`.

## Use the template without DSH

```sh
mkdir -p .github/workflows
cp assets/workflow-macos-package.yml .github/workflows/macos-package.yml
# open the file and resolve every # ADAPT marker:
#   RAW_NAME / ASSET_NAME, package directory, Node version, test and package commands
```

Then push and run it once manually before tagging:

```sh
git add .github/workflows/macos-package.yml && git commit -m "CI: macOS installer release"
git push origin main
gh workflow run macos-package.yml --ref main   # tag input empty: artifact only
```

To release, bump the version, commit, then push `main` plus only the new tag:

```sh
npm version 1.2.3 --no-git-tag-version   # keeps package-lock.json in sync
git commit -am "Release v1.2.3"
git tag v1.2.3
git push origin main v1.2.3
```

The workflow then publishes a GitHub Release with the installer, `SHA256SUMS.txt`, generated release notes (commit list, compare link, install and verification steps) and a job summary.

## What the workflow does

| Step | Purpose |
| --- | --- |
| Version guard | Fail fast unless `tag == v${package.json.version}` |
| `npm ci` + tests | Dependency install and headless test suite |
| Package | Run the project's packaging command; it must produce the installer and ad-hoc sign the app |
| Verify | Unzip, locate the `.app`, `codesign --verify --deep --strict` (verifies only, never signs) |
| Upload artifact | Keep a 30-day scratch build for manual runs |
| Release | `gh release create` (draft → upload → publish) or asset re-upload with draft repair |
| Job summary | Asset size, SHA-256, release/run links |

## Repository layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | The skill itself: recon, decisions, implementation, validation, pitfalls |
| `assets/workflow-macos-package.yml` | Drop-in GitHub Actions template (all `ADAPT` points marked) |
| `references/checklist.md` | Pre-flight, first-run and troubleshooting checklists |
| `references/stacks.md` | Adaptations for electron-builder, Tauri and custom scripts |
| `references/environment-facts.md` | Dated GitHub/Electron facts + re-verification commands |
| `scripts/validate.py` | Bundle validator (frontmatter, links, shell syntax, template guardrails, bash 3.2 pitfall) |
| `scripts/mock-release-branches.py` | Runs the template's publish step against a fake `gh` and asserts all three branches |
| `.github/workflows/ci.yml` | CI: both scripts plus actionlint/shellcheck on every push and PR |

## Requirements and limits

- **Runner:** GitHub-hosted `macos-latest` (macOS 26 arm64 as of 2026-10). Pin `macos-26` if you need a fixed image.
- **Node:** template uses Node 24; change it to match the project's `engines`.
- **Architecture:** the default template produces an Apple Silicon (arm64) installer. Intel/universal builds need a matrix or a universal build — see `references/stacks.md`.
- **Signing:** the packaging script must ad-hoc sign the app (`codesign --force --deep --sign -`); the template only verifies the signature and will fail if it is missing. Builds are not notarized, so first launch may require right-click → Open. Developer ID signing/notarization is out of scope for the template (add certificate secrets and a signing step before verification).
- **Packaging:** the template assumes an npm project whose packaging script writes `release/<name>-mac-arm64.zip`. Other stacks are supported via `references/stacks.md`; always confirm real output paths by running the packaging command locally.
- **Facts expire:** action majors, runner images and Electron behavior change. `references/environment-facts.md` records what was verified on 2026-10-27 and how to re-check.

## Contributing

Issues and pull requests are welcome. Before opening a PR:

```sh
python3 scripts/validate.py
python3 scripts/mock-release-branches.py
# plus actionlint + shellcheck on assets/workflow-macos-package.yml (CI runs all of these)
```

Keep the skill bundle valid: frontmatter `name`/`description` present, relative links working, template lint-clean, and no `$var` immediately followed by non-ASCII bytes (the macOS bash 3.2 trap).

## License

[MIT](LICENSE) © 2026 tenderzzz
