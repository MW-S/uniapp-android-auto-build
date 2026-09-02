# uniapp-android-auto-build

一套自托管的 CI/CD 流水线：把 [uni-app](https://uniapp.dcloud.net.cn/) 项目自动打包成已签名的 Android APK，并分发到可道云（WebDAV）——通过飞书消息或本地 Web 控制台触发。

[English](./README.md) | **简体中文**

[![Build & Release](https://github.com/MW-S/uniapp-android-auto-build/actions/workflows/release.yml/badge.svg)](https://github.com/MW-S/uniapp-android-auto-build/actions/workflows/release.yml)

## 工作原理

```
飞书消息（"打包 pda"）  /  Web 控制台按钮  /  命令行 --run-once
        │
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Git 更新代码        切换目标分支并 git pull + 收集本次新提交          │
│ 2. App 资源打包        默认 npm（npm run build:app），缺省时 HBuilderX  │
│                        → 自动对齐 manifest（删 plus.distribute、单行压缩）│
│                        → 自动就位到 unpackage/resources/<appid>/www     │
│ 3. 资源清理与复制      清空并复制到壳工程 assets                        │
│ 4. Android 签名构建    每次 clean assembleRelease 强制全量重建、重新签名     │
│ 5. 可道云上传          APK 以 <前缀>_YYYYmmdd_HHMMSS.apk 命名上传        │
│                        （历史版本全部保留；不会再清空远端目录）          │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
构建报告 **同一条飞书消息内逐步刷新**（⏳ 收到指令 → 🚦 进行中 → ✅/❌ 最终）
包含：每步耗时、本次新增提交 + 最近 3 次提交、APK 大小、远端路径、完整日志
```

## 功能特性

- **触发方式任选**

  - **飞书机器人**：WebSocket 长连接（无需公网回调地址），支持群聊 @ 与单聊，**同一条消息逐步刷新构建进度**，并附带完整日志。

  - **Web 控制台（Flask）**：浏览器查看项目与状态、编辑 `config.yaml`（自动校验、原子保存、自动备份旧配置）、手动触发构建、浏览历史日志。

  - **命令行**：`--run-once` / `--project X`，适配任务计划程序、cron 等定时构建场景。

- **两种资源打包方式，自动切换**

  - **npm 模式（推荐，跨平台）**：仓库 `package.json` 存在 `build:app` 脚本即启用。无需 HBuilderX 主程序常驻，Node.js 跨平台，Linux 服务器也能跑完整流水线。

  - **HBuilderX CLI 模式（兜底）**：仓库缺少 npm 脚本时回退使用，仅支持 Windows / macOS。

  - **manifest 自动对齐 HBuilderX**：npm 产物与 HBuilderX 产物默认只差一个 `plus.distribute` 发行配置块和 JSON 格式，流水线会自动删除该块、输出单行紧凑 JSON，两者 `www` 目录字节级 100% 一致（179/179 业务文件相同、manifest 字节级相同）。

- **仓库自包含改造（可选）**：把归一化脚本直接放进每个 uni-app 仓库的 `scripts/normalize-app-manifest.js`，在 `package.json` 的 `build:app` 用一行相对路径串起来，这样 git clone 到任何路径、任何机器，`npm run build:app` **一条命令**即可完成"编译 → manifest 对齐 → 资源就位到 `unpackage/resources/<appid>/www`"全部工作，不再依赖绝对路径或外部脚本。

- **多项目支持**：每个项目有独立的 git / 资源打包 / Android 壳工程 / 可道云目录，聊天触发词匹配项目（支持 `pad`、`平板`、`ipad` 等别名），可设默认项目。

- **kodcloud 上传保留历史版本**：远端文件名带秒级时间戳（`JinChanMES_PDA_20260831_013526.apk`），**不再上传前清空目录**，历史版本可追溯。

- **报告更完整**：每次自动拉取本次新增 commit、最近 3 次 commit（用于"这次打包的更新内容"），并附完整构建日志（超长截断并注明日志路径）。

- **并发保护**：同一时刻只允许一个构建任务，重复触发友好拒绝。

- **跨平台**：

  - **Windows / macOS**：npm + HBuilderX 两种模式都支持；Android 构建分别调用 `gradlew.bat` / `gradlew`。

  - **Linux**：npm、Git、资源复制、Gradle、可道云上传全部可用（可完整跑流水线）。HBuilderX 模式不支持（官方未发布 Linux 版），遇到会给出友好错误信息。

## 环境要求

| 依赖                 | 说明                                                      |
| ------------------ | ------------------------------------------------------- |
| Python 3.10+       | 3.12 实测通过                                               |
| Node.js 18+ & npm  | **npm 打包模式必需**；建议 LTS（uni-app 3.0 对旧版 Node 可能报语法错）      |
| Python 依赖          | `pip install -r requirements.txt`                       |
| Android SDK / JDK  | 由 Android 壳工程 Gradle wrapper 自行解析                       |
| 可道云 / 任意 WebDAV 服务 | 用于 APK 分发（账号密码）                                         |
| 飞书自建应用（可选）         | App ID / Secret；启用机器人能力、订阅 `im.message.receive_v1`（长连接） |
| HBuilderX（可选）      | 只在**非 npm 项目**兜底使用；npm 模式不需要安装/启动 HBuilderX             |

## 安装

```bat
git clone git@github.com:MW-S/uniapp-android-auto-build.git
cd uniapp-android-auto-build

python -m venv venv
venv\Scripts\activate          :: macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt

copy config.yaml.example config.yaml
```

`config.yaml` 含敏感信息，已被 `.gitignore` 忽略；你也可以先启动 Web 控制台在浏览器里配置。

### 让每个 uni-app 仓库"自包含"（强烈推荐）

做完下面 2 步（每个仓库各做一次，然后 commit+push），之后仓库 clone 到任何机器都能直接 `npm run build:app` 一把梭：

1. 将流水线项目里的 `scripts/REPO__normalize-app-manifest.self-contained.js` 复制为 **`<uni-app 仓库>/scripts/normalize-app-manifest.js`**。
2. 修改仓库内 `package.json` 的 1 行脚本：

   ```json
   "build:app": "uni build -p app && node scripts/normalize-app-manifest.js"
   ```

验证：

```bat
cd <uni-app 仓库>
npm install              :: 首次
npm run build:app        :: 一步搞定：编译 → manifest 对齐 → 资源就位到 unpackage/resources/<appid>/www
```

之后流水线执行 npm 模式时，会自动识别 `package.json` 已内嵌该脚本，因此流水线不会重复调用，日志里会写"归一化：build:app 已内嵌 …… 流水线不再重复调用"作为审计证据。

### 飞书应用配置（可选）

1. 在 [飞书开放平台](https://open.feishu.cn/) 创建自建应用，将 App ID / App Secret 填入 `config.yaml`。
2. 为应用开启**机器人**能力。
3. 订阅 `im.message.receive_v1` 事件，并选择**长连接（WebSocket）方式**。
4. 权限：`im:message`、`im:message.p2p_msg`、`im:message.group_at_msg`、`im:message:send_as_bot`。申请后创建并发布新版本。
5. 直接与机器人单聊，或将其拉入群聊。

## 使用方法

```bat
:: 同时启动 Web 控制台（http://127.0.0.1:8000）和飞书机器人
python main.py

:: 仅启动 Web 控制台（不连飞书，纯网页操作）
python main.py --web-only

:: 仅启动飞书机器人
python main.py --bot-only

:: 立即执行一次构建后退出（可配合任务计划程序 / cron 定时构建）
python main.py --run-once --project mes-pda

:: 列出所有已配置项目 + 打印平台诊断信息
python main.py --list

:: 自定义 Web 监听地址（默认只监听 127.0.0.1，更安全）
python main.py --host 0.0.0.0 --port 9000
```

### Web 控制台页面

| 路由                                   | 说明                                                              |
| ------------------------------------ | --------------------------------------------------------------- |
| `GET /`                              | 首页：项目列表、当前构建状态、最近构建记录                                           |
| `GET /config` · `POST /config`       | 查看 / 保存 `config.yaml`（自动校验，保存前自动备份原文件到 `config.yaml.bak.<时间戳>`） |
| `POST /build/<project_key>`          | 触发指定项目构建                                                        |
| `GET /build/<job_id>`                | 轮询构建进度 / 最终结果（配合前端「同一条进度消息」机制）                                  |
| `GET /logs` · `GET /logs/<filename>` | 构建日志列表 / 日志内容                                                   |

> 控制台**没有登录鉴权**，默认只监听 `127.0.0.1`。如需对外暴露，请务必置于带鉴权的反向代理之后。

## 打包为独立可执行文件（目标机器无需安装 Python）

使用 PyInstaller 可将整个工具打包为单文件可执行程序，方便在没有 Python 环境的打包机上运行。

> 支持 Windows / macOS / Linux 三种平台（npm 模式跨平台可用；HBuilderX 兜底模式仅限 Win/macOS）。目标平台请分别在对应平台上执行打包。

### 下载预构建版本（推荐）

每推送一个 `vX.Y.Z` 标签，GitHub Actions 会自动打包并发布新版本。直接到 [GitHub Releases](https://github.com/MW-S/uniapp-android-auto-build/releases) 下载最新版的附件：

| 附件                                               | 说明                       |
| ------------------------------------------------ | ------------------------ |
| `uniapp-android-auto-build-<版本>-<平台>-<arch>.zip` | 分发包（推荐）：含可执行文件与配置模板，解压即用 |
| `uniapp-android-auto-build[.exe]`                | 独立可执行文件                  |
| `config.yaml.example`                            | 配置模板                     |

解压后按「分发与目标机器使用」操作即可。

### 自行打包

仅在修改过代码时需要：

```bat
pip install -r requirements-dev.txt
build_exe.bat              :: macOS/Linux: ./build_exe.sh
```

产物位于 `dist/` 目录。

### 分发与目标机器使用

1. 将可执行文件与 `config.yaml.example` 放入**同一目录**。
2. 首次运行：检测到缺少 `config.yaml` 后，会自动根据模板生成并退出。
3. 填写 `config.yaml`（见「配置说明」）后再次运行，服务即启动。

运行时行为：

| 项目    | 行为                                                                                                 |
| ----- | -------------------------------------------------------------------------------------------------- |
| 配置读取  | 始终从自身所在目录读取 `config.yaml`，与当前工作目录无关                                                                |
| 日志写入  | 同级 `logs/` 目录                                                                                      |
| 命令行参数 | 与源码模式完全一致：`--web-only`、`--bot-only`、`--run-once`、`--project`、`--list`、`--config`、`--host`、`--port` |

注意事项：

- `config.yaml` 含密钥凭证，请勿公开分发。

- 个别杀毒软件可能误报 PyInstaller 生成的可执行文件，可添加信任或改用源码模式。

- 升级：下载新版压缩包解压覆盖，已有的 `config.yaml` 与 `logs/` 不受影响。

## Docker 部署（推荐用于 Linux 打包服务器）

本项目已同时提供「源码环境」、「PyInstaller 单文件 exe」、**「Docker/Compose」**三种交付形态。Docker 形态适合放在长期运行的 Linux 打包机上：环境一次性打好，之后不用再手动管理 JDK / Node / Android SDK / Python 依赖版本。

### 镜像里预装了什么（`Dockerfile`）

- `python:3.12-slim` 作为基础镜像
- **OpenJDK 17 headless**：匹配你两个壳工程的 `AGP 8.7.3 + Gradle 8.11.1`（AGP 8.x 强制 JDK17）
- **Node.js 20 LTS + npm**：uni-app npm 模式跨平台编译
- **Android commandlinetools**：预装 `platforms;android-35`、`build-tools;35.0.0`、`platform-tools`（当前两壳工程 compileSdk 都是 35）。如之后升级 compileSdk，**容器启动流水线时会自动检测壳工程版本，缺失的组件通过 sdkmanager 现场补装**（参见 `docker/ensure-android-env.sh`），不需要重新 build 镜像
- 项目源码 + `pip install -r requirements.txt`

### 目录与挂载约定

| 宿主机目录（示例） | 容器内路径 | 作用 |
|---|---|---|
| `./runtime/config/config.yaml` | `/app/runtime-config/config.yaml`（只读） | 配置文件与飞书/可道云凭证；**容器会优先读取这个挂载路径，找不到才回退为源码目录下的 `config.yaml`** |
| `./runtime/logs/` | `/app/logs`（读写） | 每个项目/每次构建的完整日志，便于排查 |
| `./runtime/repos/pda-submit` `/runtime/repos/Jinchang-Pad` | `/repos/*`（读写） | uni-app 源码仓库 + Android 壳工程，**config.yaml 里请使用 `/repos/...` 作为项目路径** |
| named volume `gradle-cache` | `/opt/gradle-cache` | Gradle wrapper 下载、依赖缓存，避免每次构建重新下载 |
| named volume `npm-cache` | `/opt/npm-cache` | npm 包缓存（你两项目 node_modules 仍在仓库自身，这是全局 HTTP 缓存） |
| named volume `android-sdk` | `/opt/android-sdk` | **最重要**：Android SDK，现场补装的 build-tools/ndk 都会保存在这里，容器重启不丢失 |

### 启动步骤（Docker Compose，推荐）

```bash
# 1. 拷贝环境变量模板并编辑
cp .env.example .env
vim .env       # 至少修改 REPOS_ROOT / BUILDER_CONFIG_DIR 指向宿主机实际路径

# 2. 在 BUILDER_CONFIG_DIR 下准备 config.yaml（路径以 .env 中指定为准）
#    建议先从仓库的 config.yaml.example 复制一份，把项目路径全部改成 /repos/... 开头：
#        git.repo_dir: '/repos/pda-submit'
#        android.project_dir: '/repos/pda-submit/APP_Debug/JinChanMES PDA'
mkdir -p ./runtime/config ./runtime/logs ./runtime/repos
cp config.yaml.example ./runtime/config/config.yaml
vim ./runtime/config/config.yaml

# 3. Build 镜像（首次或代码更新后执行）
docker compose build

# 4. 启动后台常驻（Web 控制台 + 飞书）
docker compose up -d

# 5. 查看日志 / 健康检查
docker compose logs -f
docker compose ps   # 健康状态通过 python main.py --list 判断

# 6. 一次性手动触发构建（不进入长驻）
docker compose run --rm builder --run-once --project mes-pda
```

Web 控制台默认映射在宿主机 `http://127.0.0.1:8000`，可通过 `.env` 的 `BUILDER_HOST`/`BUILDER_PORT` 修改。

### 只有源码的单机 Docker 快速构建 / 运行（不用 compose）

```bash
# 构建镜像
docker build -t uniapp-android-builder:latest .

# 双服务
docker run --rm -it -p 127.0.0.1:8000:8000 \
  -v $(pwd)/runtime/config:/app/runtime-config:ro \
  -v $(pwd)/runtime/logs:/app/logs:rw \
  -v $(pwd)/runtime/repos:/repos:rw \
  -v builder_gradle-cache:/opt/gradle-cache:rw \
  -v builder_npm-cache:/opt/npm-cache:rw \
  -v builder_android-sdk:/opt/android-sdk:rw \
  -e TZ=Asia/Shanghai \
  uniapp-android-builder:latest
```

### 常见坑 & 排错

| 现象 | 原因/解法 |
|---|---|
| Gradle 报 `SDK location not found` | 通常是 `ANDROID_SDK_ROOT` 未生效或 Android SDK volume 为空；先 `docker compose run --rm builder --list` 确认能正常启动，再查看容器 `ls /opt/android-sdk/platforms/` 是否有 `android-35`。空 volume 会触发首次 sdkmanager 自动补装（会联网，耐心等 2~5 分钟） |
| sdkmanager 一直提示 license 未接受 | 镜像启动时已自动把 license 写入 `$ANDROID_SDK_ROOT/licenses`，如果是你手动挂载了旧的 android-sdk volume 且不含 license，可以进容器执行一次：`yes | sdkmanager --licenses` |
| Gradle 报 `JAVA_HOME is invalid` | 默认 JAVA_HOME 固定为 `/usr/lib/jvm/java-17-openjdk-amd64`（x86_64）；如果你的 CPU 是 ARM（含 Apple Silicon / 阿里云 ARM 服务器），Docker 会自动拉 arm64 层，届时在 compose 的 environment 里把 JAVA_HOME 设为 `/usr/lib/jvm/java-17-openjdk-arm64` 即可 |
| 镜像体积大（~4GB）属于正常 | Android SDK（含 platform、build-tools）+ JDK + Node 本身很大；如果要减小，可以把 Android SDK 换成只装当前项目所需版本、或者把 SDK 挂 volume 不在镜像里预装（不推荐，首次启动会慢到不可接受） |
| Docker 部署后，HBuilderX 兜底步骤失败打印提示 | 是正常的；Linux 无 HBuilderX 版本。请务必把 uni-app 仓库做成「自包含」（`scripts/normalize-app-manifest.js` + package.json 脚本内嵌），流水线会用 npm 模式完整跑通，不依赖 HBuilderX |
| 容器内 git pull 提示认证失败 | 挂在 `/repos` 下的本地仓库必须有可用的凭据：SSH key（挂载 `$HOME/.ssh`）或 HTTPS credential helper；或者把 `/repos` 指向一份从你 CI 里同步出来的、已经做过 fetch 的裸镜像仓库 |
| 容器启动立刻退出，提示找不到 config.yaml | 说明挂载的 `/app/runtime-config/` 目录中没有 `config.yaml`；你可以先把 `config.yaml.example` 复制进去再启动，或加 `--config` 指向明确路径 |

### 以后升级 compileSdk / buildTools / NDK 怎么办？

**不需要重新 build Docker 镜像。**流水线每次跑 Android 构建之前，会执行 `docker/ensure-android-env.sh <壳工程目录>`，该脚本：
1. 解析 `App/build.gradle` 里的 `compileSdk / buildToolsVersion / ndkVersion`；
2. 检查 `$ANDROID_SDK_ROOT` 下是否存在对应目录；
3. 缺失时自动调用 `sdkmanager --install` 把缺的组件安装到共享 volume，并打印「Installing missing SDK component: ...」日志。

因此，当你把某个壳工程的 `compileSdk` 从 35 升到 36 时，**第一次构建会慢几分钟**（安装 android-36 + 对应 build-tools），之后所有后续构建就和本地一样快了。

## 配置说明

完整注释示例见 [config.yaml.example](./config.yaml.example)。主要字段：

| 字段                                                         | 说明                                                      |
| ---------------------------------------------------------- | ------------------------------------------------------- |
| `feishu.app_id` / `app_secret`                             | 飞书自建应用凭证（可选）                                            |
| `feishu.trigger_keywords`                                  | 全局触发关键词，如 `打包`、`构建`（命中后再匹配项目别名）                         |
| `default_project`                                          | 可选；只发「打包」时默认构建的项目 key；不填则回复项目列表                         |
| `projects[].key` / `name` / `aliases`                      | 项目标识 / 展示名 / 飞书聊天触发词（如 `["pad","平板","ipad"]`）           |
| `projects[].git.repo_dir` / `branch`                       | uni-app 本地仓库路径与分支                                       |
| `projects[].hbuilderx.cli_path`                            | HBuilderX `cli.exe` 路径（npm 模式可不填，但建议保留用于兜底）             |
| `projects[].hbuilderx.project_name` / `appid`              | HBuilderX 项目名 / uni-app appid（`__UNI__XXXXXXX`）         |
| `projects[].android.project_dir`                           | Android 壳工程根目录（需含 `gradlew.bat` / `gradlew`）            |
| `projects[].android.assets_dir`                            | 资源目标目录，如 `App/src/main/assets/apps/__UNI__XXX`（复制前会被清空） |
| `projects[].android.apk_output`                            | 相对 `project_dir` 的 APK 输出目录，找不到时自动检查 Gradle 默认输出        |
| `projects[].kodcloud.webdav_url` / `username` / `password` | WebDAV 地址与账号密码                                          |
| `projects[].kodcloud.remote_dir` / `apk_prefix`            | 上传目录 / APK 文件名前缀（历史版本全部保留在该目录）                          |

> 小提示：Windows 路径含反斜杠，YAML 中请用**单引号**包裹，例如 `project_dir: 'D:\projects\uniapp-android'`。

## 流水线步骤详解

| 步骤           | 执行内容                                                                                                                                                                                                                                                                                                                                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Git 更新代码     | 校验仓库有效性 → 必要时切换分支 → `git pull` → 收集「本次新增提交」与「最近 3 次提交」                                                                                                                                                                                                                                                                                            |
| App 资源打包     | 自动判断 npm 或 HBuilderX：• npm：`node_modules` 不存在时自动 `npm install --prefer-offline` → `npm run build:app`；识别到仓库已内嵌 normalize 脚本就不再二次调用。• HBuilderX：`cli project open` + `cli publish --platform APP --type appResource`；HBuilderX 主程序未启动导致的"0 退出码假成功"有新鲜度校验兜底。• 最终 manifest 必对齐（删 `plus.distribute` + 单行紧凑）、资源必就位到 `unpackage/resources/<appid>/www`。 |
| 资源清理与复制      | 清空壳工程 `assets_dir`（处理 Windows 只读文件），整目录复制后校验 `www/manifest.json` 存在。                                                                                                                                                                                                                                                                              |
| Android 签名构建 | 跨平台调用 `gradlew.bat`（Windows）/`gradlew`（macOS/Linux，先自动 `chmod +x`），**每次都执行** **`clean assembleRelease`** **强制全量重建并重新签名**；报告里会注明「每次构建前执行 clean 全量重建」，从而确保 APK 文件修改时间、签名信息每次都刷新、文件名相同时也会是重新生成的新产物。找不到配置 `apk_output` 会自动回退 Gradle 默认输出目录。                                                                                                           |
| 可道云上传        | 远端目录不存在自动创建；以 `前缀_YYYYmmdd_HHMMSS.apk` 命名上传；上传后校验远端文件哈希/大小；**不删除旧版本**。                                                                                                                                                                                                                                                                            |

## 日志与测试

```bat
:: 构建日志（每次构建一个文件，文件名带项目 key 与时间戳）
logs\build_<项目key>_<时间戳>.log

:: 运行单元测试（配置加载、项目匹配、manifest 对齐、manifest 归一化脚本输出等）
python -m pytest tests/ -v
```

## 目录结构

```
├── main.py                        # 入口：Web 控制台 + 飞书机器人（双服务），支持 --web-only/--bot-only/--run-once/--list/--host/--port
├── start.bat                      # 快速启动脚本（源码模式，Windows）
├── start.sh                       # 快速启动脚本（源码模式，macOS/Linux）
├── build_exe.bat / build_exe.sh   # 打包独立可执行文件（PyInstaller）
├── uniapp-android-auto-build.spec # PyInstaller 打包配置
├── config.yaml.example            # 配置模板（多项目）
├── requirements.txt
├── requirements-dev.txt           # 开发依赖（含 PyInstaller、pytest）
├── scripts/
│   ├── REPO__normalize-app-manifest.self-contained.js
│   │                                # 「仓库自包含」版 normalize 脚本：复制到每个 uni-app 仓库的 scripts/ 下使用
│   ├── normalize-app-manifest.js  # 流水线 fallback 版 normalize 脚本（显式传 <repo_dir>）
│   └── how_to_make_repo_self_contained.md  # 改造 uni-app 仓库的图文步骤
├── bot/
│   └── feishu_bot.py              # 飞书机器人（WebSocket 长连接），同一条消息逐步刷新进度状态
├── pipeline/
│   ├── config.py                  # 配置加载校验（含 JSONC src/manifest.json）、项目别名匹配
│   ├── runner.py                  # 流水线编排：on_progress 回调、步骤进度、日志落盘
│   ├── build_manager.py           # 单任务并发控制（全局一构）
│   ├── git_step.py                # 步骤1：分支切换、git pull、新 commit / 最近 3 commit 收集
│   ├── hbuilderx_step.py          # 步骤2：智能 npm 优先 + HBuilderX CLI 兜底 + manifest 对齐
│   ├── copy_resources_step.py     # 步骤3：资源复制到壳工程 assets（只读文件 chmod 兼容）
│   ├── android_build_step.py      # 步骤4：Gradle release 构建（跨平台 gradlew，无产物自动 clean）
│   ├── kodcloud_upload_step.py    # 步骤5：WebDAV 上传（目录不存在自动创建、保留历史版本、上传校验）
│   └── common.py                  # StepResult 通用结构
├── web/                           # Flask Web 控制台（模板 + 静态资源）
├── tests/                         # pytest 单元测试：配置、manifest 对齐字节级一致性、脚本跨仓库性等
└── logs/                          # 构建日志（已加入 git 忽略）
```

## 常见问题

| 现象                                                                 | 可能原因与处理                                                                                                                  |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| 运行 `npm run build:app` 后 manifest 仍有差异                             | 一般是没用自包含脚本（绝对路径/外部脚本问题）。按「让每个 uni-app 仓库"自包含"」章节做 2 步后，manifest MD5 必与 HBuilderX 原版字节级一致（已通过 MD5 + 180 文件逐文件 MD5 比对实测）。  |
| HBuilderX 步骤退出码 0 但产物未刷新                                           | **绝大多数场景已用 npm 模式避开了这个坑**。兜底使用时：检查 HBuilderX 主程序是否启动、`project_name` 是否与 HBuilderX 工程列表名称严格一致。                            |
| Android 构建成功但报告写了"UP-TO-DATE，沿用 APK"                               | 正常：资源内容与上次一致，Gradle 不重写 APK。若 APK 文件被你手动删了，流水线会自动 `clean assembleRelease` 重建。                                            |
| 上传失败 401 / 403                                                     | 可道云账号密码错误，或未开启 WebDAV 服务；也可能是新目录短暂索引延迟（脚本已做轮询重试，仍失败请检查 WebDAV 地址结尾是否加 `/`）。                                              |
| 配置解析报 `unknown escape character`                                   | Windows 路径写在了双引号里，请改用单引号包裹，例如 `project_dir: 'D:\projects\uniapp-demo'`。                                                  |
| 飞书机器人连上线但收不到消息 / 回复无权限                                             | 事件订阅未选择**长连接**方式；缺少 `im.message.receive_v1` 事件；缺少 `im:message` / `im:message:send_as_bot` 权限；或应用版本未发布。群聊里请 @ 机器人，单聊则直接发。 |
| 飞书 `[ERROR] processor not found, type: im.message.message_read_v1` | 无害：机器人读了你发送的消息，飞书推送"已读回执"事件，我们没注册回执处理器；不影响构建触发和结果回复。                                                                     |
| Linux 服务器想跑完整流水线                                                   | 使用 npm 模式 + Android Gradle 即可全链路可用。HBuilderX 模式在 Linux 不支持（官方没有 Linux 版本），会返回一段友好错误提示并给出切换建议。                            |

