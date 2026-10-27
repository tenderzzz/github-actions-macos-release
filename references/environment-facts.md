# Environment facts (verified 2026-10-27 — they expire, re-verify before use)

The workflow depends on GitHub- and Electron-side facts that change over time. **Never write versions from memory.** Re-run these checks before adapting the template to a new project.

## Re-verification commands

```sh
# Current major version of each action (decides the uses: ...@vN suffix)
for r in actions/checkout actions/setup-node actions/upload-artifact actions/cache; do
  printf '%-24s ' "$r"; gh api "repos/$r/releases/latest" --jq '.tag_name'
done

# macOS runner labels -> image / architecture
gh api repos/actions/runner-images/contents/README.md --jq '.content' | base64 -d | grep -E 'macos-(latest|2[0-9])'

# setup-node features (e.g. node-version-file support)
gh api repos/actions/setup-node/contents/README.md --jq '.content' | base64 -d | grep -i 'node-version-file' | head -3

# Node release schedule (is the target major still supported?)
curl -fsSL https://raw.githubusercontent.com/nodejs/release/main/schedule.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('\n'.join(f\"{k}: phase={v.get('phase')} lts={v.get('lts')} eol={v.get('end')}\" for k,v in d.items()))"

# Packaging toolchain versions
npm view electron version 2>/dev/null
npm view @electron/packager version engines 2>/dev/null

# Repo Actions state and default token permissions
gh api repos/{owner}/{repo}/actions/permissions
gh api repos/{owner}/{repo}/actions/permissions/workflow
```

## Verified on 2026-10-27

| Fact | Value | Source |
| --- | --- | --- |
| `macos-latest` | macOS 26 **arm64** (`macos-26-arm64` image, Xcode CLT 27); `macos-15` is also arm64; `macos-14` retires 2026-11-02 | actions/runner-images README; GitHub changelogs |
| Action majors | `checkout@v7`, `setup-node@v7`, `upload-artifact@v7`, `cache@v6` (all `node24` runtime); Node 20-based actions are gone | action releases / `action.yml` |
| Node on hosted runners | Node 24.x / npm 11.x preinstalled; setup-node installs the latest Node 24 patch | run logs from a real workflow (v24.22.x) |
| `GITHUB_TOKEN` | A repo-level read-only default does **not** block a workflow that declares `permissions: contents: write`; fork PRs cannot elevate | GitHub docs: workflow syntax / automatic token authentication |
| `gh` CLI | Preinstalled on GitHub-hosted runners (2.102.x); `gh release create` with asset files = draft → upload → publish | runner image README; gh manual |
| Electron | 42+ npm packages **no longer download a binary during install**; `ELECTRON_SKIP_BINARY_DOWNLOAD` was removed; packaging tools fetch Electron themselves | Electron breaking changes |
| `@electron/packager` | 18.4.4 with Electron 45 packaged successfully both locally and on a macOS 26 arm64 runner | verified run (body-journal v0.1.19 CI) |
| Codesign/zip | Ad-hoc `codesign --force --deep --sign -` needs no keychain; `.app` bundles must be zipped with `ditto -c -k --keepParent` | Apple codesign docs; verified run |
| Billing | Standard runners are free for public repos; macOS minutes are billed 10× for private repos | GitHub billing docs |

Measured reference run (public repo; the **build/test/package/artifact path** was exercised by a manual `workflow_dispatch` run — the `gh release` publish branch has so far only been validated locally with a mocked `gh`): GitHub-hosted `macos-26-arm64`, Node 24.22.1, npm 11.19.1, 80/80 tests, packaging + signature verification + 125 MB artifact upload in **71 s** wall time. Instance: [tenderzzz/body-journal](https://github.com/tenderzzz/body-journal) — [run 40465779354](https://github.com/tenderzzz/body-journal/actions/runs/40465779354) (`workflow_dispatch`, `tag` empty).

## Official links

- Runner images and labels: https://github.com/actions/runner-images
- Workflow syntax and `permissions`: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Automatic token authentication: https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication
- gh release: https://cli.github.com/manual/gh_release_create and https://cli.github.com/manual/gh_release_upload
- Electron breaking changes: https://www.electronjs.org/docs/latest/breaking-changes
- Electron code signing: https://www.electronjs.org/docs/latest/tutorial/code-signing
- Actions cache scoping: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- Billing: https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions

## Upgrade policy

- Bump action majors only after reading release notes; validate with a manual build run before tagging a release.
- When GitHub announces a runner image retirement, update the pinned label before it breaks.
- Electron/packager upgrades: get `npm run package` green locally, merge, then do one tag release to confirm.
- Update this file (and the "verified on" date) whenever the facts above change.
