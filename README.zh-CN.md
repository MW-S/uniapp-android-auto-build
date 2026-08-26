# uniapp-android-auto-build

一套自托管的 CI/CD 流水线：把 [uni-app](https://uniapp.dcloud.net.cn/) 项目自动打包成已签名的 Android APK，并分发到可道云（WebDAV）——通过飞书消息或本地 Web 控制台触发。

[English](./README.md) | **简体中文**

## 工作原理

```
飞书消息（"打包 demo"）  /  Web 控制台按钮
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ 1. Git 更新代码        切换目标分支并 git pull            │
│ 2. HBuilderX 资源打包  本地离线打包出 App 资源            │
│ 3. 资源清理与复制      清空并复制到壳工程 assets          │
│ 4. Android 签名构建    gradlew.bat assembleRelease        │
│ 5. 可道云上传          APK 按时间戳命名上传到 WebDAV      │
└──────────────────────────────────────────────────────────┘
        │
        ▼
构建报告回复到飞书会话 / 展示在 Web 控制台
APK 以 <前缀>_YYYYmmdd_HHMMSS.apk 保存在可道云
```

## 功能特性

- **飞书机器人触发**——发送包含触发关键词（如 `打包`、`构建`）和项目名/触发词的消息，机器人实时逐步更新构建进度，并回复最终报告。基于飞书 WebSocket 长连接，**无需公网回调地址**。
- **Web 控制台**（Flask）——查看项目与构建状态、在浏览器中编辑 `config.yaml`（自动校验、原子保存并自动备份）、手动触发构建、浏览构建日志。
- **多项目支持**——每个项目拥有独立的 git 仓库 / HBuilderX 工程 / Android 壳工程 / 可道云目标目录，通过聊天消息中的触发词匹配；可配置默认项目。
- **并发保护**——同一时刻仅允许一个构建任务，重复触发会被友好拒绝。
- **全程可追溯**——每次构建都会写入完整日志 `logs/build_<key>_<时间戳>.log`，可在 Web 控制台浏览；报告包含各步骤耗时、本次拉取的新提交、APK 大小与远端路径。
- **智能增量构建**——已有 APK 产物时执行 `assembleRelease`，产物被删除时自动回退为 `clean assembleRelease` 全量构建。

## 环境要求

| 依赖 | 说明 |
|---|---|
| Windows | Android 构建步骤依赖 `gradlew.bat`；HBuilderX CLI 输出按 GBK 解析 |
| Python 3.10+ | |
| HBuilderX | 本机安装且提供 CLI（`cli.exe`）；打包时 HBuilderX 主程序需保持运行 |
| Android 壳工程 | 包含 `gradlew.bat`，且 Gradle 中已配置 release 签名 |
| 可道云 / WebDAV | 用于 APK 分发的 WebDAV 账号 |
| 飞书自建应用 | 需要 App ID / App Secret，启用机器人能力与 `im.message.receive_v1` 事件 |

## 安装

```bat
git clone git@github.com:MW-S/uniapp-android-auto-build.git
cd uniapp-android-auto-build

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy config.yaml.example config.yaml
```

随后填写 `config.yaml`（也可以先启动 Web 控制台，在浏览器中配置）。`config.yaml` 含敏感信息，已被 git 忽略，仓库中只保留 `config.yaml.example` 模板。

### 飞书应用配置

1. 在[飞书开放平台](https://open.feishu.cn/)创建自建应用，将 App ID / App Secret 填入 `config.yaml`。
2. 为应用开启**机器人**能力。
3. 订阅 `im.message.receive_v1` 事件，并选择**长连接（WebSocket）方式**。
4. 开通所需 IM 权限、发布应用版本，然后直接与机器人单聊或将其拉入群聊。

## 使用方法

```bat
:: 同时启动 Web 控制台（http://127.0.0.1:8000）和飞书机器人
python main.py
:: 或直接双击运行：start.bat

:: 仅启动 Web 控制台
python main.py --web-only

:: 仅启动飞书机器人
python main.py --bot-only

:: 立即执行一次构建后退出（适合配合任务计划程序定时构建）
python main.py --run-once --project demo-app

:: 列出所有已配置项目
python main.py --list

:: 自定义 Web 监听地址
python main.py --host 0.0.0.0 --port 9000
```

### Web 控制台页面

| 路由 | 说明 |
|---|---|
| `GET /` | 首页：项目列表、当前构建状态、最近构建记录 |
| `GET /config` · `POST /config` | 查看 / 保存 `config.yaml`（自动校验，保存前自动备份） |
| `POST /build/<project_key>` | 触发指定项目的构建 |
| `GET /build/<job_id>` | 轮询构建进度 / 最终结果 |
| `GET /logs` · `GET /logs/<filename>` | 构建日志列表 / 日志内容 |

> 控制台**没有登录鉴权**，默认只监听 `127.0.0.1`。如需对外暴露，请务必置于带鉴权的反向代理之后。

## 配置说明

完整注释的示例见 [config.yaml.example](./config.yaml.example)。主要字段：

| 字段 | 说明 |
|---|---|
| `feishu.app_id` / `app_secret` | 飞书自建应用凭证 |
| `feishu.trigger_keywords` | 全局触发关键词（如 `打包`、`构建`） |
| `default_project` | 可选；未匹配到项目时构建的默认项目 |
| `projects[].key` / `name` / `aliases` | 项目标识、显示名与聊天触发词 |
| `projects[].git.repo_dir` / `branch` | uni-app 本地仓库路径与要构建的分支 |
| `projects[].hbuilderx.cli_path` | HBuilderX `cli.exe` 完整路径 |
| `projects[].hbuilderx.project_name` / `appid` | HBuilderX 中的项目名 / uni-app appid（`__UNI__XXXXXXX`） |
| `projects[].android.project_dir` | Android 壳工程根目录（需含 `gradlew.bat`） |
| `projects[].android.assets_dir` | 资源目标目录，如 `app/src/main/assets/apps/__UNI__XXX`（复制前会被清空） |
| `projects[].android.apk_output` | 相对 `project_dir` 的 APK 输出目录 |
| `projects[].kodcloud.webdav_url` / `username` / `password` | WebDAV 地址与账号密码 |
| `projects[].kodcloud.remote_dir` / `apk_prefix` | 远端上传目录 / APK 文件名前缀 |

> 提示：Windows 路径含反斜杠，YAML 中请用**单引号**包裹，例如 `project_dir: 'D:\projects\uniapp-android'`。

## 流水线步骤详解

| 步骤 | 执行内容 |
|---|---|
| git 更新代码 | 校验仓库有效性，必要时切换到配置的分支，执行 `git pull`，并收集本次新增提交（展示在报告中） |
| HBuilderX 资源打包 | 执行 `cli project open` + `cli publish --platform APP --type appResource`，并校验 `unpackage/resources/<appid>` 产物确实已刷新 |
| 资源清理与复制 | 清空 `assets_dir`（兼容 Windows 只读文件），整目录复制打包产物，并校验 `www/manifest.json` 存在 |
| Android 签名构建 | 执行 `gradlew.bat assembleRelease`（无产物时自动 `clean` 全量），取最新生成的 APK；签名依赖壳工程 Gradle 配置 |
| 可道云上传 | 远端目录不存在则自动创建，以 `<前缀>_YYYYmmdd_HHMMSS.apk` 命名上传，上传后校验远端文件存在 |

## 日志与测试

```bat
:: 构建日志（每次构建一个文件）
logs\build_<项目key>_<时间戳>.log

:: 运行单元测试
python -m pytest tests/ -v
```

## 目录结构

```
├── main.py                  # 入口：Web 控制台 + 飞书机器人（双服务）
├── start.bat                # 快速启动脚本
├── config.yaml.example      # 配置模板
├── requirements.txt
├── bot/
│   └── feishu_bot.py        # 飞书机器人（WebSocket 长连接）
├── pipeline/
│   ├── config.py            # 配置加载校验、项目匹配
│   ├── runner.py            # 流水线编排与日志记录
│   ├── build_manager.py     # 单任务并发控制
│   ├── git_step.py          # 步骤1：分支切换与拉取
│   ├── hbuilderx_step.py    # 步骤2：HBuilderX 离线打包
│   ├── copy_resources_step.py   # 步骤3：资源复制到壳工程
│   ├── android_build_step.py    # 步骤4：Gradle release 构建
│   └── kodcloud_upload_step.py  # 步骤5：WebDAV 上传
├── web/                     # Flask 控制台（模板 + 静态资源）
├── tests/                   # pytest 单元测试
└── logs/                    # 构建日志（已加入 git 忽略）
```

## 常见问题

| 现象 | 可能原因与处理 |
|---|---|
| HBuilderX 步骤退出码为 0 但产物未刷新 | HBuilderX 主程序未启动，或 `project_name` 与 HBuilderX 工程列表中的名称不一致 |
| Android 步骤构建成功但 APK 未变化 | Gradle UP-TO-DATE 缓存——产物缺失时流水线会自动 `clean` 全量构建；否则检查 `assets_dir` 路径是否正确 |
| 上传失败（401/403） | 可道云账号密码错误，或未开启 WebDAV 服务 |
| 配置解析报 "unknown escape character" | Windows 路径写在了双引号里，请改用单引号包裹 |
| 飞书机器人收不到消息 | 事件订阅未选择长连接方式、缺少 `im.message.receive_v1` 事件，或应用版本未发布 |
