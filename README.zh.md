# github-actions-macos-release

> 一个 agent skill + 可直接套用的工作流模板：用 GitHub Actions 构建并发布 macOS 桌面应用安装包。

[![CI](https://github.com/tenderzzz/github-actions-macos-release/actions/workflows/ci.yml/badge.svg)](https://github.com/tenderzzz/github-actions-macos-release/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.md) | **中文**

这个仓库把一条在真实项目上验证过的发布流水线打包成两种复用形式：

1. **DSH skill**（DeepSeek Harness 的技能）：agent 在处理 macOS 发布工作流前会加载的作业手册，包含侦察清单、设计决策、验证流程、已知坑和模板。
2. **独立的工作流模板**：`assets/workflow-macos-package.yml` 可以直接复制到任意仓库的 `.github/workflows/`，不用 DSH 也能用。

在一个真实的 Electron 45 应用上，GitHub Actions 手动运行（macOS 26 arm64 runner）完成了 80/80 测试、打包、签名校验，并上传了 125 MB 的 artifact，耗时约 71 秒。同一工作流已配置为 tag 触发发布；`gh release` 发布分支目前只用 mock 的 `gh` 在本地验证过，等待首次真实 tag 发版。**不需要 Apple 开发者证书，也不需要配置任何仓库 secret**——构建使用 ad-hoc 签名，首次打开可能需要在 Finder 里右键「打开」。

## 为什么值得用

- **标签触发、默认安全**：推 `v*` 才构建+测试+发布；手动运行默认只构建，填了 tag 才动 Release。tag 与 `package.json` 版本不一致时几秒内失败，不浪费构建时间。
- **不会上传坏包**：上传前会解压产物并验证签名，打不开的 `.app` 到不了用户手里。
- **无需密钥**：`permissions: contents: write` 就够；ad-hoc 档位不需要 PAT、证书或公证账号。
- **重跑安全**：draft → 上传 → 发布，失败可修，不用删 tag/Release 重来。

## 作为 DSH skill 安装

DSH 从 `~/.dsh/skills/<name>/SKILL.md`（以及项目级 `.dsh/skills/`）发现 skill。直接把本仓库克隆到用户技能目录：

```sh
git clone https://github.com/tenderzzz/github-actions-macos-release.git \
  ~/.dsh/skills/github-actions-macos-release
```

不用重启：新增 skill 后下一轮对话就会出现在技能目录里。任务匹配时 agent 会自动加载，也可以明确说「用 `github-actions-macos-release` skill」。以后更新：`git -C ~/.dsh/skills/github-actions-macos-release pull`。

只给单个仓库用的话，克隆到 `<repo>/.dsh/skills/github-actions-macos-release` 即可。

## 不用 DSH，直接套模板

```sh
mkdir -p .github/workflows
cp assets/workflow-macos-package.yml .github/workflows/macos-package.yml
# 打开文件，逐个处理 # ADAPT 注释：
#   RAW_NAME / ASSET_NAME、打包目录、Node 版本、测试与打包命令
```

先推上去手动跑一次，确认无误再打标签：

```sh
git add .github/workflows/macos-package.yml && git commit -m "CI: macOS installer release"
git push origin main
gh workflow run macos-package.yml --ref main   # tag 留空：只出 artifact
```

正式发版：改版本 → 提交 → 推 `main` 和这一条 tag：

```sh
npm version 1.2.3 --no-git-tag-version   # 同时同步 package-lock.json
git commit -am "Release v1.2.3"
git tag v1.2.3
git push origin main v1.2.3
```

之后工作流会自动创建 GitHub Release：安装包、`SHA256SUMS.txt`、自动生成的 release notes（提交列表、compare 链接、安装与校验步骤）以及运行摘要。

## 工作流做了什么

| 步骤 | 作用 |
| --- | --- |
| 版本校验 | tag 必须等于 `v` + `package.json` 版本，否则立即失败 |
| `npm ci` + 测试 | 装依赖、跑 headless 测试 |
| 打包 | 执行项目自己的打包命令；打包脚本必须产出安装包并给 app 做 ad-hoc 签名 |
| 校验 | 解压、找到 `.app`、`codesign --verify --deep --strict`（只验证，不签名） |
| 上传 artifact | 手动构建产物保留 30 天 |
| 发布 | `gh release create`（draft → 上传 → 发布），或已存在时覆盖资产并修复 draft |
| 运行摘要 | 产物大小、SHA-256、Release/运行链接 |

## 仓库结构

| 路径 | 作用 |
| --- | --- |
| `SKILL.md` | skill 本体：侦察、决策、实现、验证、坑 |
| `assets/workflow-macos-package.yml` | 可直接套用的 GitHub Actions 模板（标好 `ADAPT` 点） |
| `references/checklist.md` | 上线前、首次运行、故障排查清单 |
| `references/stacks.md` | electron-builder、Tauri、自定义脚本的适配方式 |
| `references/environment-facts.md` | 带日期的 GitHub/Electron 事实 + 重新核对命令 |
| `scripts/validate.py` | skill bundle 校验器（frontmatter、链接、shell 语法、模板护栏、bash 3.2 坑） |
| `scripts/mock-release-branches.py` | 用假 `gh` 跑模板的发布步骤，断言三条分支行为 |
| `.github/workflows/ci.yml` | CI：两个脚本 + actionlint/shellcheck，每次 push/PR 都跑 |

## 要求与限制

- **Runner**：GitHub 托管 `macos-latest`（截至 2026-10 为 macOS 26 arm64）。需要固定就写 `macos-26`。
- **Node**：模板用 Node 24，按项目 `engines` 改。
- **架构**：默认只出 Apple Silicon（arm64）包；Intel/通用包需要 matrix 或 universal 构建，见 `references/stacks.md`。
- **签名**：打包脚本必须给 app 做 ad-hoc 签名（`codesign --force --deep --sign -`），模板只负责验证，缺签名会直接失败。未公证，首次打开可能需右键「打开」。Developer ID 签名+公证不在模板范围内（需要证书 secrets 并在验证前加签名步骤）。
- **打包方式**：模板假设 npm 项目、打包脚本产出 `release/<name>-mac-arm64.zip`；其它技术栈按 `references/stacks.md` 适配，并且一定要先在本地跑一遍确认真实产物路径。
- **环境事实会过期**：action 主版本、runner 镜像、Electron 行为都在变。`references/environment-facts.md` 记录了 2026-10-27 核对的事实与复核命令。

## 贡献

欢迎 issue 和 PR。提交前请跑：

```sh
python3 scripts/validate.py
python3 scripts/mock-release-branches.py
# 以及用 actionlint + shellcheck 检查 assets/workflow-macos-package.yml（CI 会跑全部）
```

保持 skill bundle 有效：frontmatter 的 `name`/`description` 齐全、相对链接可用、模板 lint 通过、不要出现「`$var` 后紧跟非 ASCII 字符」的写法（macOS bash 3.2 的坑）。

## 许可证

[MIT](LICENSE) © 2026 tenderzzz
