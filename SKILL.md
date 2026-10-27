---
name: github-actions-macos-release
description: Add or repair a GitHub Actions workflow that builds a macOS desktop-app installer on GitHub-hosted runners and publishes it to a GitHub Release or uploads it as an artifact.
whenToUse: Use when a desktop-app repo (Electron, Tauri, native macOS) needs CI that builds a .zip/.dmg/.pkg installer and publishes it, especially tag-triggered releases; also when an existing macOS build/release workflow fails, publishes wrong or missing assets, or lacks permission/version guardrails.
---

# macOS installer releases with GitHub Actions

A playbook for AI coding agents: turn "build a macOS installer on GitHub's macOS runners and upload it" into a reusable, re-runnable, mistake-proof pipeline. **This skill writes and verifies the workflow; GitHub Actions does the building and uploading.** A real-world instance of the bundled template: [tenderzzz/body-journal](https://github.com/tenderzzz/body-journal) (Electron 45; a manual run on a macOS 26 arm64 runner passed 80/80 tests, built and signature-verified the installer and uploaded a 125 MB artifact in ~71 s; its tag→release publish branch awaited its first real tag release at the time of writing).

## Use this skill when

- The repo ships a macOS desktop app (Electron, Tauri, native) and the user wants CI-built installers.
- Releases should be published by pushing a `v*` tag (or manually re-published/retried).
- An existing macOS build/release workflow fails, hangs, produces the wrong architecture, loses assets, or publishes from the wrong commit.
- The user wants installers downloadable from GitHub Releases without managing Apple Developer certificates.

## Do not use when

- The target is a website, server, CLI-only tool, or mobile app (nothing to install on macOS).
- The project already publishes installers through another system and the user does not want GitHub Releases.
- The user wants App Store / TestFlight distribution — that needs different signing and upload steps.
- No GitHub-hosted macOS runner is acceptable (e.g. self-hosted-only policy); adapt the idea, not the YAML.

## Reconnaissance first (do not paste the template blindly)

Run from the repo root and confirm four facts: **build command, artifact name/path, architecture, signing tier.**

```sh
# Build/package/test scripts and runtime requirements
node -p "require('./package.json').scripts" 2>/dev/null || cat pyproject.toml Cargo.toml
# What the packaging script actually produces (path, filename, arch, signing)
ls scripts/ 2>/dev/null; sed -n '1,80p' package.json
# Existing releases: naming, tag convention, asset names, signing notes in README
gh release list
gh release view <tag> --json name,tagName,isDraft,assets
# Version convention: are tag, package.json and README in sync?
git tag -l | tail -10; git log --oneline -10
# Actions enablement and default token permissions (read-only default is fine)
gh api repos/{owner}/{repo}/actions/permissions
gh api repos/{owner}/{repo}/actions/permissions/workflow
# Anything the packaging step needs that is not committed (signed resources, local caches)
cat .gitignore
```

Also read the packaging script for hardcoded local paths, signing identities, or `arch` values; those are the usual reasons a clean checkout behaves differently.

## Design decisions (settle before writing YAML)

- **Trigger.** `push: tags: ['v*']` publishes; `workflow_dispatch` builds on demand. Manual runs default to "build only, keep the artifact" and only touch a Release when a tag input is filled — this prevents accidental publishes.
- **Version guard.** The tag must equal `v` + `package.json` version. Fail *before* installing dependencies so a mismatch costs seconds, not minutes.
- **Upload target.** Release assets are the primary deliverable (stable URL, linkable from README, survives artifact expiry). Actions artifacts are only scratch output for manual test builds (retention 1–90 days).
- **Runner.** `macos-latest` (macOS 26 arm64 as of 2026-10). Pin `macos-26` when reproducibility matters, but remember GitHub retires old images.
- **Permissions.** Declare `permissions: contents: write` at workflow level. This overrides a repo-level read-only default; no PAT, no extra secret. Fork PRs cannot elevate, so keep publishing on tag pushes / manual dispatch.
- **Concurrency.** Use the *target release tag* in `concurrency.group`, not `github.ref`: tag pushes (`refs/tags/vX`) and manual re-runs (`refs/heads/main`) are different refs but write the same Release.
- **Signing tier.** Default to ad-hoc (`codesign --force --deep --sign -`): no certificate, no notarization, users may need right-click → Open on first launch. Only add Developer ID signing + notarization when the repo already has certificate secrets or the user explicitly asks — it is slower and needs an Apple Developer account.

## Implementation

1. Copy `assets/workflow-macos-package.yml` (relative to this skill's base directory) to the target repo's `.github/workflows/`, then change every `ADAPT` marker: package output directory, `RAW_NAME`/`ASSET_NAME` (the published name must be **ASCII and stable**), Node version, test command, packaging command, artifact name, release title and release-notes locale. The `.app` bundle name is discovered after unzip, so it needs no marker.
2. Keep this step order: checkout full history → print runner/toolchain → setup-node → version guard → `npm ci` → headless tests → package → unzip + `codesign --verify --deep --strict` → artifact upload → release notes → `gh` publish → job summary. The template only *verifies* the signature; if the packaging script does not ad-hoc sign the app, add `codesign --force --deep --sign -` right after packaging.
3. Publish with the runner's preinstalled `gh` CLI, not a third-party release action. `gh release create <tag> <files>` creates a draft, uploads assets, then publishes, so a failed upload never leaves a public empty release.
4. Release notes must include: install steps, commit list since the previous tag, compare link, and how to verify the SHA-256. Add `--verify-tag` so an existing tag is required.
5. Update docs: README section with the exact release commands, manual trigger, asset name; if the repo keeps a verification log, record the first real run's numbers.
6. When the stack differs from plain `npm run package`, follow `references/stacks.md` (electron-builder, Tauri, custom scripts) before adapting the template.

## Validation (not done until this passes)

1. **Lint the bundle.** From this skill's base directory run `python3 scripts/validate.py` and `python3 scripts/mock-release-branches.py`; then `actionlint -shellcheck "$(command -v shellcheck)" <template>`. If actionlint is missing, download the official release binary into `/tmp`; do not modify the system.
2. **Simulate a clean CI checkout.** `rm -rf /tmp/ci-run && mkdir -p /tmp/ci-run && git archive HEAD | tar -x -C /tmp/ci-run`, then run `npm ci && npm test && npm run package` there with the same Node major as the workflow. This catches packaging that depends on uncommitted files.
3. **Mock the publish branches.** `python3 scripts/mock-release-branches.py` extracts the template's publish step, runs it against a fake `gh`, and asserts create / re-upload published / repair draft without touching a real repository. (This is also what CI runs, so the claim is enforced.)
4. **Run a real manual build.** After pushing to the default branch, `gh workflow run <file> --ref main` with the tag input empty. Check step conclusions (build steps success, release steps skipped), artifact size, and that existing Releases are untouched.
5. **Watch the first real tag release.** `gh run watch`, then verify Release assets, `SHA256SUMS.txt` against the downloaded zip, and that previous releases are unchanged.

## Known pitfalls (roughly by frequency)

- **macOS system bash 3.2 + UTF-8 locale**: if `$var` is immediately followed by a non-ASCII byte (CJK/fullwidth punctuation such as `，` `）`), bash may swallow that byte into the variable name and fail with `unbound variable`. Always write `${var}` when non-ASCII text follows. This can hide in the default locale; test with `LANG=en_US.UTF-8` and `LANG=C.UTF-8`.
- `github.event.inputs.tag` is null on non-dispatch events. Use `${{ github.event.inputs.tag || github.ref_name }}` for fallbacks; do not build cross-event expressions around `inputs.tag`.
- Without `--verify-tag`, `gh release create` creates the tag from the default branch. Always pass `--verify-tag` when publishing an existing version.
- `gh release upload --clobber` deletes the old asset before uploading. A failed re-upload can leave the release without an installer; check `--json isDraft` and only run `gh release edit --draft=false` for drafts (running it on a published release can error).
- Action caches are scoped per ref: tag-triggered caches are rarely reused by the next tag. Do not add elaborate Electron caching; since Electron 42, `npm install` no longer downloads a binary and packaging tools fetch it themselves.
- Zip `.app` bundles with `ditto -c -k --keepParent`, never with `zip` (symlinks and metadata break).
- Do not run GUI smoke tests (Playwright driving an Electron window) in CI; keep CI to headless unit tests.
- GitHub-hosted standard runners are free for public repos; private repos bill macOS minutes at 10×.
- Keep the packaging tool and Electron versions compatible; get `npm run package` green locally before adding CI.
- Never move/reuse a published tag; never commit tokens. Set `persist-credentials: false` on checkout.

## Definition of done

- [ ] Template copied and every `ADAPT` marker resolved; asset filename stable and ASCII.
- [ ] Version guard, permissions, concurrency group and `--verify-tag` present.
- [ ] Lint passes; clean-tree simulation passes; mock publish branches pass.
- [ ] Manual workflow run is green (artifact produced, release steps skipped).
- [ ] README documents release commands; first real tag release verified (or explicitly marked pending).
- [ ] Report to the user: files changed, runner/Node/duration/asset size, which paths are still unverified, and the exact commands for the next release.

## Bundled resources

- `assets/workflow-macos-package.yml` — copy-ready workflow template with `ADAPT` markers.
- `scripts/validate.py` — bundle validator: frontmatter, links, shell syntax, template guardrails, bash 3.2 pitfall.
- `scripts/mock-release-branches.py` — runs the template's publish step against a fake `gh` and asserts all three branches.
- `references/checklist.md` — pre-flight, first-run and troubleshooting checklists.
- `references/stacks.md` — electron-builder, Tauri and custom-script adaptations.
- `references/environment-facts.md` — verified GitHub/Electron facts (dated) plus re-verification commands.
- `.github/workflows/ci.yml` — runs both scripts plus actionlint/shellcheck on every push and PR.
