# Adapting the template to other packaging stacks

The bundled template is written for the simple case: an npm project whose `npm run package` script writes `release/<name>-mac-arm64.zip`. The workflow structure (triggers, version guard, permissions, release publishing) is stack-independent; only the **build step, artifact path, architecture, and signing verification** change. Confirm actual output paths by running the packaging command once locally — the paths below are the usual conventions, not guarantees.

## Electron with `@electron/packager` (template default)

- Build: `node scripts/package.mjs` (or `npm run package`).
- Output: `.app` bundle copied out by your script; the template assumes the script zips it to `release/<name>-mac-arm64.zip` with `ditto -c -k --keepParent`.
- Signing: ad-hoc after packaging, `codesign --force --deep --sign - "App.app"`; verify with `codesign --verify --deep --strict`.
- `ADAPT`: `RAW_NAME`, `ASSET_NAME`, `release/` path, app bundle name (not needed by the template — it finds `*.app` after unzip).
- Note: Electron 42+ no longer downloads a binary during `npm install`; `@electron/packager` downloads the matching Electron release itself at packaging time. Ensure Electron and packager versions are compatible, and that the app bundle id/name match the project config.

## Electron with `electron-builder`

- Build: `npx electron-builder --mac --arm64` (or a package.json script such as `npm run dist`).
- Output: typically `dist/<product>-<version>-arm64.dmg`, `dist/<product>-<version>-arm64-mac.zip`, plus `latest-mac.yml` / `*.blockmap` if `electron-updater` is configured.
- Signing: set `CSC_IDENTITY_AUTO_DISCOVERY=false` for unsigned/ad-hoc CI builds; without a certificate electron-builder skips Developer ID signing. Verify the produced app with `codesign --verify --deep --strict` (inside a mounted dmg or the unzipped mac zip).
- `ADAPT`: publish the `.dmg` and/or the `-mac.zip` as `ASSET_NAME`; if the app uses `electron-updater`, upload `latest-mac.yml` and blockmap files too — the updater expects those exact names. Verify `hdiutil attach -nobrowse -readonly <dmg>` works and the app inside opens.
- Remove the template's `mv`/`ditto` step for `.dmg`; keep SHA-256 and signature verification (attach the dmg, then verify the `.app` inside).

## Tauri v2

- Build: `npm run tauri build -- --target aarch64-apple-darwin` (or `cargo tauri build --target ...`).
- Output: `src-tauri/target/aarch64-apple-darwin/release/bundle/macos/<App>.app` and `.../bundle/dmg/<App>.dmg` (macOS targets are configurable in `tauri.conf.json`).
- Signing: Tauri signs with the identity from `APPLE_SIGNING_IDENTITY`/config; without a certificate verify the result with `codesign --verify --deep --strict` and treat it as ad-hoc (users may need right-click → Open).
- `ADAPT`: the packaging step, output path and asset name; drop the Electron-specific assumptions. Rust toolchain setup may need `dtolnay/rust-toolchain` and caching (`Swatinem/rust-cache`) before the build step.
- Universal builds: `--target universal-apple-darwin`; otherwise run a two-entry matrix (`aarch64-apple-darwin`, `x86_64-apple-darwin`) and publish both assets with distinct names.

## Custom scripts / native tools

- Replace `Build and package` with the actual command, keep the artifact inside the repo (e.g. `release/` or `build/`), then reuse the template's rename/checksum/verify steps.
- If the installer is a `.pkg`: `pkgutil --check-signature <file>` for signature verification, and `installer -pkg <file> -target /` is *not* appropriate in CI — only inspect the header/`pkgutil --payload-files`.
- If the app is notarized: `codesign --verify --strict` plus `spctl --assess --type execute` (this requires a Developer ID certificate and `notarytool` credentials in secrets).
- If the build needs Homebrew tools: `brew install <tool>` on the runner; note that `macos-latest` images already include codesign, ditto, shasum, gh and Python 3.

## Architecture matrix

- Template default: single arm64 package (Apple Silicon only, matching most personal projects).
- For Intel + Apple Silicon: use a matrix over `macos-26` (arm64) and `macos-26-intel` (x64) — or `macos-15-intel`, since plain `macos-15` is arm64 — with architecture-specific asset names (`app-mac-arm64.zip`, `app-mac-x64.zip`), or produce one universal build (`--universal`).
- Release jobs in a matrix must upload distinct asset names; two jobs must not write the same file concurrently. Either publish from one job after downloading both artifacts, or use separate tags/releases.
