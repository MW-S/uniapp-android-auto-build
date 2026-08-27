# uniapp-android-auto-build

A self-hosted CI/CD pipeline that turns [uni-app](https://uniapp.dcloud.net.cn/) projects into signed Android APKs and distributes them to KodCloud (WebDAV) — triggered by a Feishu (Lark) chat message or a local web console.

**English** | [简体中文](./README.zh-CN.md)

## How it works

```
Feishu message ("打包 demo")  /  Web console button
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ 1. Git update          checkout target branch, git pull  │
│ 2. HBuilderX packaging publish app resources offline     │
│ 3. Copy resources      clear & copy into shell assets    │
│ 4. Android build       gradlew.bat assembleRelease       │
│ 5. KodCloud upload     APK -> WebDAV with timestamp name │
└──────────────────────────────────────────────────────────┘
        │
        ▼
Build report replied to Feishu chat / shown in web console
APK stored on KodCloud as <prefix>_YYYYmmdd_HHMMSS.apk
```

## Features

- **Feishu bot trigger** — send a message containing a trigger keyword (e.g. `打包`, `构建`) plus a project name/alias; the bot replies with real-time step-by-step progress and a final report. Based on the Feishu WebSocket long connection, **no public callback URL required**.
- **Web console** (Flask) — view projects and build status, edit `config.yaml` in the browser (validated, atomically saved with automatic backup), trigger builds manually, browse build logs.
- **Multi-project support** — each project has its own git repo / HBuilderX project / Android shell project / KodCloud target, matched by aliases in chat messages; an optional default project.
- **Concurrency guard** — only one build runs at a time; extra triggers are rejected with a friendly message.
- **Full traceability** — every build writes a complete log to `logs/build_<key>_<timestamp>.log`, browsable in the web console; reports include per-step timing, new commits pulled, APK size and remote path.
- **Smart incremental build** — runs `assembleRelease` when previous APKs exist, falls back to `clean assembleRelease` when outputs were deleted.

## Prerequisites

| Requirement | Notes |
|---|---|
| Windows | Android step relies on `gradlew.bat`; HBuilderX CLI output is read as GBK |
| Python 3.10+ | |
| HBuilderX | Installed locally with CLI (`cli.exe`); the HBuilderX main program should be running when packaging |
| Android shell project | Must contain `gradlew.bat` and a valid release signing config in Gradle |
| KodCloud / WebDAV | Account with WebDAV access for APK distribution |
| Feishu custom app | App ID / App Secret with bot + `im.message.receive_v1` event enabled |

## Installation

```bat
git clone git@github.com:MW-S/uniapp-android-auto-build.git
cd uniapp-android-auto-build

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy config.yaml.example config.yaml
```

Then fill in `config.yaml` (or start the web console first and configure via the browser — see below). `config.yaml` contains secrets and is git-ignored by design; only `config.yaml.example` is committed.

### Feishu app setup

1. Create a custom app in the [Feishu Open Platform](https://open.feishu.cn/) and copy its App ID / App Secret into `config.yaml`.
2. Enable the **Bot** capability for the app.
3. Subscribe to the `im.message.receive_v1` event using **long connection (WebSocket) mode**.
4. Grant the required IM permissions, publish the app version, then chat with the bot directly or add it to a group.

## Usage

```bat
:: Start web console (http://127.0.0.1:8000) + Feishu bot together
python main.py
:: or simply: start.bat

:: Web console only
python main.py --web-only

:: Feishu bot only
python main.py --bot-only

:: Run one build immediately and exit (for cron / task scheduler)
python main.py --run-once --project demo-app

:: List all configured projects
python main.py --list

:: Custom web address
python main.py --host 0.0.0.0 --port 9000
```

### Web console routes

| Route | Description |
|---|---|
| `GET /` | Dashboard: project list, current build status, recent builds |
| `GET /config` · `POST /config` | View / save `config.yaml` (validated, auto backup before saving) |
| `POST /build/<project_key>` | Trigger a build for a project |
| `GET /build/<job_id>` | Poll build progress / final result |
| `GET /logs` · `GET /logs/<filename>` | Build log list / log content |

> The console has **no authentication** and binds `127.0.0.1` by default. If you expose it to a network, put it behind a reverse proxy with auth.

## Build a standalone executable (no Python required)

Use PyInstaller to package the whole tool into a single-file executable so it can run on build machines without a Python environment.

> The pipeline only supports Windows (see Prerequisites), and so does the packaged exe — build on Windows.

### Build

```bat
pip install -r requirements-dev.txt
build_exe.bat
```

The script installs PyInstaller automatically if missing. Output under `dist\`:

| File | Description |
|---|---|
| `uniapp-android-auto-build.exe` | Standalone executable (console app, ~43 MB) |
| `config.yaml.example` | Config template (copied automatically by the script) |

### Distribute & run on the target machine

1. Put `uniapp-android-auto-build.exe` and `config.yaml.example` into the **same folder**.
2. Run the exe for the first time: it detects the missing config, generates `config.yaml` from the template, and exits.
3. Fill in `config.yaml` (see Configuration reference), then run the exe again to start the services.

Runtime behavior:

| Item | Behavior |
|---|---|
| Config location | The exe always reads `config.yaml` from its own directory, regardless of the current working directory |
| Log location | `logs\` folder next to the exe |
| CLI arguments | Identical to source mode: `--web-only`, `--bot-only`, `--run-once`, `--project`, `--list`, `--config`, `--host`, `--port` |
| Startup time | The first launch needs a few seconds to self-extract; subsequent launches are faster |

Notes:

- `config.yaml` contains credentials — never distribute it publicly.
- Some antivirus software may falsely flag PyInstaller executables; add an exclusion or fall back to source mode.
- To upgrade, rebuild with `build_exe.bat` and replace the exe; your existing `config.yaml` and `logs\` are unaffected.

## Configuration reference

See [config.yaml.example](./config.yaml.example) for a fully commented sample. Key fields:

| Field | Description |
|---|---|
| `feishu.app_id` / `app_secret` | Feishu custom app credentials |
| `feishu.trigger_keywords` | Global keywords that activate the bot (e.g. `打包`, `构建`) |
| `default_project` | Optional; project built when no project is matched |
| `projects[].key` / `name` / `aliases` | Project identity and chat trigger words |
| `projects[].git.repo_dir` / `branch` | Local uni-app repo path and branch to build |
| `projects[].hbuilderx.cli_path` | Full path to HBuilderX `cli.exe` |
| `projects[].hbuilderx.project_name` / `appid` | Project name in HBuilderX / uni-app appid (`__UNI__XXXXXXX`) |
| `projects[].android.project_dir` | Android shell project root (with `gradlew.bat`) |
| `projects[].android.assets_dir` | Resource target dir, e.g. `app/src/main/assets/apps/__UNI__XXX` (cleared before copy) |
| `projects[].android.apk_output` | APK output dir relative to `project_dir` |
| `projects[].kodcloud.webdav_url` / `username` / `password` | WebDAV endpoint and credentials |
| `projects[].kodcloud.remote_dir` / `apk_prefix` | Remote upload dir / APK filename prefix |

> Tip: Windows paths contain backslashes. In YAML wrap them in **single quotes**, e.g. `project_dir: 'D:\projects\uniapp-android'`.

## Build pipeline details

| Step | What happens |
|---|---|
| Git update | Validates the repo, checks out the configured branch if needed, `git pull`, and collects the new commits pulled (shown in the report) |
| HBuilderX packaging | `cli project open` + `cli publish --platform APP --type appResource`; verifies the output under `unpackage/resources/<appid>` is actually refreshed |
| Copy resources | Clears `assets_dir` (handles read-only files on Windows), copies the packaged resources, verifies `www/manifest.json` exists |
| Android build | `gradlew.bat assembleRelease` (or `clean assembleRelease` when no APK exists), picks the newest APK; signing comes from the shell project's Gradle config |
| KodCloud upload | Creates the remote dir if missing, uploads as `<prefix>_YYYYmmdd_HHMMSS.apk`, then verifies the remote file exists |

## Logs & tests

```bat
:: Build logs (one file per build)
logs\build_<project_key>_<timestamp>.log

:: Run unit tests
python -m pytest tests/ -v
```

## Project structure

```
├── main.py                  # Entry: web console + Feishu bot (dual service)
├── start.bat                # Quick start script (source mode)
├── build_exe.bat            # Build standalone executable (PyInstaller)
├── uniapp-android-auto-build.spec  # PyInstaller build configuration
├── config.yaml.example      # Configuration template
├── requirements.txt
├── requirements-dev.txt     # Dev dependencies (incl. PyInstaller)
├── bot/
│   └── feishu_bot.py        # Feishu bot (WebSocket long connection)
├── pipeline/
│   ├── config.py            # Config loading/validation, project matching
│   ├── runner.py            # Pipeline orchestration & log recording
│   ├── build_manager.py     # Single-build concurrency control
│   ├── git_step.py          # Step 1: branch checkout & pull
│   ├── hbuilderx_step.py    # Step 2: HBuilderX offline packaging
│   ├── copy_resources_step.py   # Step 3: copy resources into shell project
│   ├── android_build_step.py    # Step 4: Gradle release build
│   └── kodcloud_upload_step.py  # Step 5: WebDAV upload
├── web/                     # Flask console (templates + static)
├── tests/                   # pytest unit tests
└── logs/                    # Build logs (git-ignored)
```

## Troubleshooting

| Symptom | Likely cause & fix |
|---|---|
| HBuilderX step: exit code 0 but resources not refreshed | The HBuilderX main program is not running, or `project_name` doesn't match the project list in HBuilderX |
| Android step: build succeeds but APK unchanged | Gradle UP-TO-DATE cache — the pipeline auto-detects missing APKs and runs a `clean` build; otherwise check `assets_dir` path |
| Upload fails with 401/403 | Wrong KodCloud username/password or WebDAV not enabled |
| Config parse error mentioning "unknown escape character" | Windows path in double quotes — use single quotes instead |
| Feishu bot receives nothing | Event subscription not in long connection mode, missing `im.message.receive_v1`, or app version not published |
