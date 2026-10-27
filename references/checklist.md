# Checklist and troubleshooting

## Before the first run

- [ ] `python3 scripts/validate.py` and `actionlint -shellcheck "$(command -v shellcheck)" assets/workflow-macos-package.yml` are clean.
- [ ] Every `ADAPT` marker in the template is resolved (package dir, `RAW_NAME`/`ASSET_NAME`, Node version, test/package commands, artifact name, release title, notes locale).
- [ ] Clean-tree simulation passes: `rm -rf /tmp/ci-run && mkdir -p /tmp/ci-run && git archive HEAD | tar -x -C /tmp/ci-run`, then the same `npm ci && npm test && npm run package` with the workflow's Node major.
- [ ] `python3 scripts/mock-release-branches.py` passes (create / existing published / leftover draft branches).
- [ ] README release commands agree with the version guard (`tag == v${package.json.version}`).
- [ ] Repo default token is read-only? Workflow declares `permissions: contents: write` (no repo setting change needed).
- [ ] Existing release asset names are not silently changed (README download links must keep working).

## First manual run (tag input empty, artifact only)

```sh
gh workflow run macos-package.yml --ref main
gh run list --workflow=macos-package.yml --limit 1
gh run watch <run-id>
gh run view <run-id> --json jobs --jq '.jobs[].steps[] | "\(.number) \(.name): \(.conclusion)"'
```

- [ ] `Verify tag matches package.json version`, `Generate release notes`, `Publish GitHub Release` are `skipped`.
- [ ] `Upload build artifact` succeeded; artifact size is plausible (Electron apps are usually 80–150 MB).
- [ ] Job summary contains the asset size and SHA-256.
- [ ] Existing releases untouched (asset digests unchanged).
- [ ] No `unbound variable`, no permission 403 in the logs.

## First real tag release

- [ ] Tag equals `v` + `package.json` version, otherwise the guard fails by design.
- [ ] Release page shows title, notes, installer and `SHA256SUMS.txt`.
- [ ] Downloaded zip matches `shasum -a 256` in `SHA256SUMS.txt`.
- [ ] `codesign --verify --deep --strict` passes on the unzipped app; the app opens (right-click → Open for ad-hoc builds).
- [ ] Previous releases unchanged; `latest` points at the new version.

## Troubleshooting

| Symptom | Usual cause | Fix |
| --- | --- | --- |
| Tag push does not trigger the workflow | Workflow file absent from the tagged commit; tag created by `GITHUB_TOKEN` (does not trigger runs); Actions disabled; tag does not match `v*` | Push the tag from a normal account; make sure the tag commit contains the workflow; `gh api repos/{owner}/{repo}/actions/permissions` |
| `Resource not accessible by integration` / 403 creating a release | Missing `permissions: contents: write`; org policy; fork PR token is read-only | Add permissions; publish on tag push or manual dispatch, not on fork PRs |
| `unbound variable`, variable name followed by garbled bytes | macOS bash 3.2 + UTF-8 locale merges the first byte of a non-ASCII char into `$var` | Write `${var}` or add a space; reproduce with `LANG=en_US.UTF-8` |
| `Tag vX does not match package.json version vY` | Version bumped in only one place | Bump `package.json` (and lockfile) first, commit, then tag; `npm version <ver> --no-git-tag-version` keeps the lockfile in sync |
| Packaging step cannot find inputs / empty output | Packaging command or output path changed; packaging relies on uncommitted files | Reproduce in a clean tree; fix `ADAPT` paths |
| `No .app bundle found` / signature verification fails | Output is not an `.app` layout, or signing configuration changed | Inspect the unzipped layout; re-run the packaging command locally and `codesign --verify` |
| Downloaded app is "damaged" / will not open | Ad-hoc signed and not notarized, Gatekeeper blocks it | Right-click → Open; for a smooth first launch, add Developer ID signing + notarization |
| `bad CPU type in executable` | Architecture mismatch (arm64 build on x64 or vice versa) | Align runner arch and packaging `arch`; for both architectures use a matrix or a universal build |
| App broken after unzip (symlinks lost) | Used system `zip` on `.app` | Use `ditto -c -k --keepParent` |
| `gh: command not found` | Not a GitHub-hosted runner | Use GitHub-hosted runners, or install gh / call the REST API |
| Assets gone after a failed `gh release upload --clobber` | clobber deletes before uploading | Re-run the workflow to rebuild; back up important assets first |
| `gh release edit --draft=false` errors | Run against an already published release | Check `--json isDraft` first; only edit drafts |
| Cache misses between tags | Actions caches are scoped per ref | Expected; do not add elaborate caching for tag builds |
| Artifact download expired | Artifacts are kept 1–90 days | Long-term distribution belongs in Release assets |

## Recovery principles

- Prefer re-running: manual dispatch with the tag filled replaces same-named assets (confirm this is acceptable for users who already downloaded).
- Do not delete releases or tags to "start over" — it breaks existing links (and immutable releases forbid it).
- A failed publish can leave a draft; re-running uploads assets and publishes it automatically, or publish it from the web UI.
