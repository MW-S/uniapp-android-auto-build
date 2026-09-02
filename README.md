# uniapp-android-auto-build

A self-hosted CI/CD pipeline that packages [uni-app](https://uniapp.dcloud.net.cn/) projects into signed Android APKs and distributes them to KodCloud (WebDAV) — triggered via Feishu (Lark) chat, a local web console, or the CLI.

**English** | [简体中文](./README.zh-CN.md)

[![Build & Release](https://github.com/MW-S/uniapp-android-auto-build/actions/workflows/release.yml/badge.svg)](https://github.com/MW-S/uniapp-android-auto-build/actions/workflows/release.yml)

## How it works

```
Feishu ("build pda")  /  Web button  /  CLI --run-once
        │
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. Git update         switch branch, git pull, collect new commits         │
│ 2. App resource pack  npm by default (fallback HBuilderX)                 │
│                       → auto-align manifest (drop plus.distribute + minify)│
│                       → stage into unpackage/resources/<appid>/www        │
│ 3. Copy resources     clean shell assets and copy the www directory in    │
│ 4. Android build      gradlew(.bat) assembleRelease (auto clean on miss)  │
│ 5. KodCloud upload    APK name <prefix>_YYYYmmdd_HHMMSS.apk               │
│                       (history preserved; remote directory no longer wiped)│
└────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
Build report progressively updated **inside the same Feishu message**:
  ⏳ received → 🚦 in progress per step → ✅/❌ final report
Includes: step timing, new commits + last 3 commits, APK size, remote path, full build log.
```

## Features

- **Choose how you trigger builds**
  - **Feishu bot** – WebSocket long-connection (no public callback URL needed); supports @mentions in groups and 1-on-1 chat; the bot **progressively updates the same chat message** as the build runs and appends the complete build log in the final report.
  - **Flask web console** – view projects and live build status; edit `config.yaml` in the browser (validated, atomically saved with automatic backup); trigger builds manually; browse build history logs.
  - **Command line** – `--run-once --project X` fits Task Scheduler, cron, Jenkins, or any periodic build system.
- **Two resource-packaging paths, auto-picked**
  - **npm mode (recommended, cross-platform)** – enabled automatically when the uni-app repo declares a `build:app` script. No need to install or keep HBuilderX running; Node.js works everywhere, so the full pipeline also runs on Linux servers.
  - **HBuilderX CLI mode (fallback)** – used only when the repo has no npm script. Windows and macOS only.
  - **Manifest byte-for-byte alignment with HBuilderX** – npm output and HBuilderX output differ by a single `plus.distribute` distribution block and JSON whitespace. The pipeline drops that block and rewrites the file as single-line compact JSON, guaranteeing the produced `www` directory is byte-identical to HBuilderX (179/179 business files match + manifest MD5 matches, verified by per-file MD5 across 180 files).
- **"Self-contained" uni-app repos (recommended)** – place a tiny `scripts/normalize-app-manifest.js` directly in each uni-app repo and chain it on the existing `build:app` script with a relative path. After that, anyone cloning the repo to **any path on any machine** can run `npm run build:app` and get: compile → manifest alignment → staged into `unpackage/resources/<appid>/www` — all with a single command and zero dependency on absolute paths or external scripts.
- **Multi-project** – each project has its own git repo / build path / Android shell project / KodCloud target directory; chat messages match projects by alias (`pad`, `tablet`, `ipad`, …); optional default project when only the trigger keyword is sent.
- **History-preserving KodCloud upload** – APK filenames carry second-level timestamps (`JinChanMES_PDA_20260831_013526.apk`); the remote directory is **no longer wiped before upload**, so every historical version stays downloadable.
- **Richer build reports** – each build automatically collects the commits introduced by the pull plus the most recent 3 commits (so reviewers know what changes are in the APK), and includes the complete build log (truncated with a path note if very long).
- **Concurrency guard** – only one build is allowed to run globally; concurrent triggers receive a friendly "busy, please try later" reply.
- **Cross-platform**
  - **Windows / macOS**: both npm + HBuilderX modes work; Android build invokes `gradlew.bat` or `gradlew` (auto `chmod +x`) respectively.
  - **Linux**: npm, git, resource copy, Gradle, and WebDAV upload all work end-to-end. HBuilderX mode is not supported (DCloud does not ship a Linux build) and returns a helpful error with a switch-to-npm suggestion.

## Prerequisites

| Dependency | Notes |
|---|---|
| Python 3.10+   | Tested on 3.12 |
| Node.js 18+ & npm | **Required for npm mode**; use an LTS release (old Node versions commonly cause `??=` / optional chain syntax errors in uni-app 3.0) |
| Python packages | `pip install -r requirements.txt` |
| Android SDK / JDK | Resolved by your Android shell project Gradle wrapper |
| KodCloud / any WebDAV service | Account + password for APK distribution |
| Feishu custom app (optional) | App ID / Secret with bot ability + `im.message.receive_v1` event via long connection |
| HBuilderX (optional) | Only required as the fallback for repos that don't have a `build:app` npm script; not needed for npm mode |

## Installation

```bash
git clone git@github.com:MW-S/uniapp-android-auto-build.git
cd uniapp-android-auto-build

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
# source venv/bin/activate

pip install -r requirements.txt

cp config.yaml.example config.yaml    # Windows:  copy config.yaml.example config.yaml
```

`config.yaml` contains secrets and is intentionally `.gitignore`'d. You can also start the web console first and configure everything from the browser.

### Making each uni-app repo "self-contained" (highly recommended)

Perform these 2 steps in each of your uni-app repos (once per repo), then commit and push. After that anyone who clones the repo to any machine can run `npm run build:app` and get a fully HBuilderX-aligned build:

1. Copy `scripts/REPO__normalize-app-manifest.self-contained.js` from this pipeline project into **`<uni-app repo>/scripts/normalize-app-manifest.js`**.
2. Change **one line** in the repo's `package.json`:
   ```json
   "build:app": "uni build -p app && node scripts/normalize-app-manifest.js"
   ```

Verify:
```bash
cd <uni-app repo>
npm install          # first time only
npm run build:app    # one command does: compile → manifest align → stage into unpackage/resources/<appid>/www
```

When the pipeline runs npm mode, it now auto-detects that `package.json` already embeds the normalizer and therefore won't invoke it a second time. The build log will contain an audit line like *"Normalizer already embedded in build:app — pipeline will not re-run it."*

### Feishu app setup (optional)

1. Create a custom app on the [Feishu Open Platform](https://open.feishu.cn/), paste its App ID / App Secret into `config.yaml`.
2. Enable the **Bot** capability.
3. Subscribe to the `im.message.receive_v1` event and choose **long-connection (WebSocket)** mode.
4. IM permissions required: `im:message`, `im:message.p2p_msg`, `im:message.group_at_msg`, `im:message:send_as_bot`. Request them, create an app version, and publish it.
5. Chat directly with the bot 1-on-1, or invite it to groups (in groups the bot only sees @mentions by default).

## Usage

```bash
# Start both: web console (http://127.0.0.1:8000) + Feishu bot
python main.py

# Web console only (no Feishu, pure browser workflow)
python main.py --web-only

# Feishu bot only
python main.py --bot-only

# Run exactly one build immediately then exit (great for cron / Task Scheduler)
python main.py --run-once --project mes-pda

# Print platform diagnostics + list all configured projects
python main.py --list

# Custom web host/port (default bind 127.0.0.1:8000 for safety)
python main.py --host 0.0.0.0 --port 9000
```

### Web console routes

| Route | Description |
|---|---|
| `GET /` | Dashboard: project list, current build status, recent builds |
| `GET /config` · `POST /config` | View / save `config.yaml` (validated, auto-backup to `config.yaml.bak.<timestamp>`) |
| `POST /build/<project_key>` | Trigger a build for a project |
| `GET /build/<job_id>` | Poll build progress / final JSON result (pairs with the same-message progress update flow in Feishu) |
| `GET /logs` · `GET /logs/<filename>` | Build log listing / log content |

> The console has **no authentication** and binds `127.0.0.1` by default. If you expose it beyond localhost, always put it behind an authenticated reverse proxy.

## Build a standalone executable (no Python required on the target)

PyInstaller packages the entire tool into a single binary, handy for build machines without a Python runtime.

> Works on Windows / macOS / Linux in npm mode; the HBuilderX fallback is Windows/macOS only. Run the packaging step on the target platform to get a native binary.

### Download pre-built releases (recommended)

GitHub Actions automatically builds and publishes on every `vX.Y.Z` tag. Grab the latest assets from [GitHub Releases](https://github.com/MW-S/uniapp-android-auto-build/releases):

| Asset | Description |
|---|---|
| `uniapp-android-auto-build-<version>-<os>-<arch>.zip` | Distribution bundle (recommended): binary + config template, extract and run |
| `uniapp-android-auto-build[.exe]` | Standalone single-file binary |
| `config.yaml.example` | Config template |

Extract, then follow "Distribute and run on the target machine" below.

### Build it yourself

Only needed if you modified the code:

```bash
pip install -r requirements-dev.txt
# Windows
build_exe.bat
# macOS / Linux
./build_exe.sh
```

Outputs land in `dist/`.

### Distribute and run on the target machine

1. Drop the binary and `config.yaml.example` into the **same folder**.
2. Run the binary once; it detects the missing config, generates `config.yaml` from the template, and exits.
3. Fill in `config.yaml` (see Configuration reference) and run the binary again — services start.

Runtime behavior:

| Item | Behavior |
|---|---|
| Config location | Always reads `config.yaml` from its own directory, never from the working directory |
| Log location | `logs/` folder next to the binary |
| CLI flags | Identical to source mode: `--web-only`, `--bot-only`, `--run-once`, `--project`, `--list`, `--config`, `--host`, `--port` |

Notes:
- Never distribute `config.yaml` publicly — it carries credentials.
- Some antivirus engines flag PyInstaller binaries as false positives; add an exclusion or fall back to the source install.
- To upgrade, overwrite the binary from a newer release; your existing `config.yaml` and `logs/` are untouched.

## Configuration reference

See [config.yaml.example](./config.yaml.example) for the fully commented template. Key fields:

| Field | Description |
|---|---|
| `feishu.app_id` / `app_secret` | Feishu custom app credentials (optional) |
| `feishu.trigger_keywords` | Global keywords that activate the bot (e.g. `打包`, `构建`) before project alias matching |
| `default_project` | Optional; project key to build when the sender wrote only the keyword without a project name; omit to reply with the project list instead |
| `projects[].key` / `name` / `aliases` | Stable project identifier / display name / chat alias words that select it (e.g. `["pad","tablet","ipad"]`) |
| `projects[].git.repo_dir` / `branch` | Local path of the uni-app git repo + branch to build |
| `projects[].hbuilderx.cli_path` | Full path to HBuilderX `cli.exe` (optional for npm mode; useful if you want the fallback) |
| `projects[].hbuilderx.project_name` / `appid` | Project name in HBuilderX workspace / uni-app appid (`__UNI__XXXXXXX`) |
| `projects[].android.project_dir` | Android shell project root (must contain `gradlew.bat` on Windows, or executable `gradlew` on Unix) |
| `projects[].android.assets_dir` | Resource destination directory e.g. `App/src/main/assets/apps/__UNI__XXX`; directory is wiped before every copy |
| `projects[].android.apk_output` | APK output directory relative to `project_dir`; if empty, Gradle's default `build/outputs/apk/release` is auto-tried |
| `projects[].kodcloud.webdav_url` / `username` / `password` | WebDAV endpoint + credentials |
| `projects[].kodcloud.remote_dir` / `apk_prefix` | Remote upload directory / APK filename prefix; every historical APK lives under this directory, nothing is deleted |

> Pro tip: Windows paths include backslashes — in YAML wrap them in **single quotes**, e.g. `project_dir: 'D:\projects\uniapp-android'`.

## Pipeline step-by-step

| Step | What happens |
|---|---|
| Git update | Validate the repo → switch branch if configured → `git pull` → collect "commits introduced this build" plus the most recent 3 commits |
| App resource pack | Auto-select npm or HBuilderX:<br>• npm: auto-install deps if `node_modules` is missing (`npm install --prefer-offline`) → `npm run build:app`; if the repo's `build:app` already includes the normalizer script, the pipeline does **not** call it again (avoiding duplicate work and duplicated log lines).<br>• HBuilderX: `cli project open` + `cli publish --platform APP --type appResource`; a freshness check on `www/manifest.json` catches the infamous "exit code 0 but nothing built" caused by HBuilderX not running.<br>• In both modes the produced manifest is guaranteed aligned (strip `plus.distribute` + single-line compact JSON) and staged into `unpackage/resources/<appid>/www`. |
| Copy resources | Wipe the shell project's `assets_dir` (Windows read-only files handled gracefully), copy the `www` directory tree in, then verify `www/manifest.json` exists. |
| Android build | Cross-platform: `gradlew.bat assembleRelease` on Windows, or `chmod +x gradlew && ./gradlew assembleRelease` on Unix; if the expected APK is missing afterwards it auto-re-runs `clean assembleRelease`; Gradle `UP-TO-DATE` hits are accepted and annotated in the report. |
| KodCloud upload | Create the remote directory if it doesn't exist; upload as `<prefix>_YYYYmmdd_HHMMSS.apk`; verify the remote file size after upload. **Old versions are never deleted**. |

## Logs & tests

```bash
# Build logs — one file per build, named with the project key and timestamp
logs/build_<project_key>_<timestamp>.log

# Run unit tests (config parsing, project alias matching, manifest byte-alignment, normalizer output correctness, ...)
python -m pytest tests/ -v
```

## Project structure

```
├── main.py                          # Entry: web console + Feishu bot (dual services). Flags: --web-only/--bot-only/--run-once/--list/--host/--port
├── start.bat                        # Quick launcher (source mode, Windows)
├── start.sh                         # Quick launcher (source mode, macOS/Linux)
├── build_exe.bat / build_exe.sh     # Build PyInstaller single-file binary per platform
├── uniapp-android-auto-build.spec   # PyInstaller spec
├── config.yaml.example              # Multi-project config template
├── requirements.txt
├── requirements-dev.txt             # Dev deps: PyInstaller + pytest
├── scripts/
│   ├── REPO__normalize-app-manifest.self-contained.js
│   │                                  # "Repo self-contained" normalizer template. Copy as <uni-app repo>/scripts/normalize-app-manifest.js to use.
│   ├── normalize-app-manifest.js    # Pipeline fallback normalizer (takes <repo_dir> explicitly)
│   └── how_to_make_repo_self_contained.md   # Step-by-step guide to onboard a uni-app repo to the self-contained pattern
├── bot/
│   └── feishu_bot.py                # Feishu WebSocket bot; progressively updates the same chat message with step progress
├── pipeline/
│   ├── config.py                    # Config load + validation (handles JSONC src/manifest.json), project alias resolution
│   ├── runner.py                    # Pipeline orchestration, on_progress callbacks, per-step progress reporting, log writer
│   ├── build_manager.py             # Global single-build concurrency guard
│   ├── git_step.py                  # Step 1: branch checkout, git pull, collect new + last 3 commits
│   ├── hbuilderx_step.py            # Step 2: smart npm-first packaging with HBuilderX CLI fallback + manifest alignment
│   ├── copy_resources_step.py       # Step 3: clean-and-copy into the Android shell project (read-only file safe)
│   ├── android_build_step.py        # Step 4: Gradle release build (cross-platform gradlew, auto-clean on missing APK)
│   ├── kodcloud_upload_step.py      # Step 5: WebDAV upload (auto-mkdir, timestamp names, history-preserving, verify)
│   └── common.py                    # Shared StepResult type
├── web/                             # Flask web console (templates + static assets)
├── tests/                           # pytest suite: config, manifest byte-alignment, normalizer cross-repo behavior, etc.
└── logs/                            # Build logs (git-ignored)
```

## Troubleshooting

| Symptom | Likely cause & fix |
|---|---|
| After `npm run build:app` the manifest still differs from HBuilderX | You're probably not running the self-contained normalizer inside the uni-app repo (absolute path / external script issues). Perform the 2-step "self-contained" setup once per repo; byte-level MD5 equality with the HBuilderX baseline is guaranteed (verified by 180-file per-file MD5 comparison). |
| HBuilderX step: exit code 0 but resources are not refreshed | The npm path avoids this pitfall almost entirely. When using HBuilderX as a fallback: confirm the HBuilderX main program is launched and that `project_name` exactly matches the workspace name in HBuilderX. |
| Android build succeeds but the report says *"UP-TO-DATE, reusing existing APK"* | Normal behavior — Gradle correctly skipped rebuilding because the inputs didn't change. If the APK file was externally deleted the pipeline auto-runs `clean assembleRelease` to rebuild it. |
| Upload fails with 401/403 | Wrong KodCloud username/password, or WebDAV not enabled for the account. Newly-created remote directories can also have a brief indexing delay (the script already retries; if it still fails, double-check that your WebDAV URL ends with `/`). |
| Config parse error: *"unknown escape character …"* | You wrapped a Windows backslash path in double quotes. Use single quotes: `project_dir: 'D:\projects\uniapp-android'`. |
| Feishu bot shows as *connected* but never receives messages / never replies | Event subscription is not in long-connection mode, `im.message.receive_v1` event is missing, required IM scopes are missing, or the app version that grants them has not been published. In group chats remember to @ the bot; direct chat works without an @. |
| Feishu `[ERROR] processor not found, type: im.message.message_read_v1` | Harmless noise. Feishu pushed a read-receipt event that we don't register a handler for; it has no effect on build triggers or report replies. |
| I want a full pipeline that runs on a Linux server | Enable npm mode + Gradle — every step works end-to-end on Linux. HBuilderX mode is not available (no official Linux build) and will return a helpful error plus the switch-to-npm suggestion. |
