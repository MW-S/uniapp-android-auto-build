import json
import os
import shutil
import subprocess
import sys
import time

from .common import StepResult
from .config import repo_resources_dir

CLI_ENCODING = "gbk" if sys.platform.startswith("win") else "utf-8"
NPM_ENCODING = "utf-8"

OPEN_TIMEOUT = 300
PACK_TIMEOUT = 1800          # npm 编译比 HBuilderX CLI 长一些
NPM_INSTALL_TIMEOUT = 900
FRESHNESS_WAIT_TIMEOUT = 90
FRESHNESS_POLL_INTERVAL = 2


def _pipeline_dir():
    # 返回流水线项目根（包含 scripts/ 目录）
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(cmd, *, timeout, cwd=None, encoding=CLI_ENCODING):
    """list cmd 传参，避免 shell 差异。返回 CompletedProcess。"""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace",
        timeout=timeout,
    )


def _output(proc):
    parts = [proc.stdout or "", proc.stderr or ""]
    return "\n".join(part.strip() for part in parts if part.strip())


def _npm_cmd():
    """跨平台 npm 可执行文件名。"""
    if sys.platform.startswith("win"):
        return "npm.cmd"
    return "npm"


def _node_cmd():
    if sys.platform.startswith("win"):
        return "node.exe"
    return "node"


def _package_has_build_app(repo_dir):
    pkg = os.path.join(repo_dir, "package.json")
    if not os.path.isfile(pkg):
        return False
    try:
        with open(pkg, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        return bool(
            isinstance(obj, dict)
            and isinstance(obj.get("scripts"), dict)
            and isinstance(obj["scripts"].get("build:app"), str)
        )
    except (OSError, json.JSONDecodeError):
        return False


def _run_npm_mode(cfg):
    """npm run build:app → manifest 归一化 → 资源就位 三联动。

    归一化脚本优先级：仓库自带的 scripts/normalize-app-manifest.js（推荐，相对路径可随仓库提交分发）
    → 否则回退到流水线自带 scripts/normalize-app-manifest.js（兼容）。
    """
    repo_dir = cfg["git"]["repo_dir"]
    resources_dir = repo_resources_dir(cfg)
    www_dir = os.path.join(resources_dir, "www")
    final_manifest = os.path.join(www_dir, "manifest.json")

    # 1) 仓库内脚本（优先）：零参数，脚本用 __dirname/.. 自定位仓库根
    repo_norm_script = os.path.join(repo_dir, "scripts", "normalize-app-manifest.js")
    if os.path.isfile(repo_norm_script):
        norm_script = repo_norm_script
        norm_args = []  # 相对路径/自定位模式，不传参
    else:
        # 2) 兼容：流水线自带脚本，需显式传 <repo_dir>
        norm_script = os.path.join(_pipeline_dir(), "scripts", "normalize-app-manifest.js")
        norm_args = [repo_dir]
        if not os.path.isfile(norm_script):
            return StepResult.fail_result(
                "未找到 manifest 归一化脚本：仓库内既无 scripts/normalize-app-manifest.js，"
                f"流水线也缺失 fallback 脚本 {norm_script}"
            )

    old_mtime = os.path.getmtime(final_manifest) if os.path.isfile(final_manifest) else 0.0
    pack_start = time.time()

    logs = [f"打包方式：npm（{os.path.basename(repo_dir)}）"]
    # 注意：仓库 package.json 里的 build:app 通常会写成 "uni build -p app && node scripts/normalize-app-manifest.js"
    # （自包含模式，一行搞定）——这种情况下 npm run build:app 就已经完成了"归一化+就位"，
    # 流水线不应再调用一次 normalize 脚本（避免重复执行日志，且操作本身是幂等的但会造成混乱）。
    # 判断方式：用仓库内 package.json 的 scripts.build:app 字符串是否显式调用了 normalize-app-manifest 脚本。
    pkg_path = os.path.join(repo_dir, "package.json")
    build_app_invokes_norm = False
    if os.path.isfile(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8-sig") as fh:
                pkg_obj = json.load(fh)
            script_text = (
                pkg_obj.get("scripts", {}) if isinstance(pkg_obj, dict) else {}
            ).get("build:app", "") or ""
            build_app_invokes_norm = "normalize-app-manifest" in script_text
        except (OSError, json.JSONDecodeError):
            build_app_invokes_norm = False

    if build_app_invokes_norm:
        logs.append(
            "归一化：package.json 的 build:app 已内嵌 node scripts/normalize-app-manifest.js，"
            "npm run build:app 执行时会一并完成 manifest 归一化与资源就位；流水线不再重复调用。"
        )
        norm_script = None
        norm_args = []
    elif norm_args:
        logs.append(f"归一化脚本来源：流水线 fallback -> {norm_script}（显式传参仓库路径）")
    else:
        logs.append(f"归一化脚本来源：仓库内自包含 -> {norm_script}（零参数，相对路径自定位，随仓库分发可用）")

    # 1) node_modules 不存在时先 npm install（带离线优先，避免每次装）
    nm = os.path.join(repo_dir, "node_modules")
    if not os.path.isdir(nm):
        logs.append("node_modules 未找到，先执行 npm install --prefer-offline")
        try:
            inst = _run(
                [_npm_cmd(), "install", "--prefer-offline", "--no-audit", "--no-fund"],
                timeout=NPM_INSTALL_TIMEOUT,
                cwd=repo_dir,
                encoding=NPM_ENCODING,
            )
        except subprocess.TimeoutExpired:
            return StepResult.fail_result(
                f"npm install 超时（{NPM_INSTALL_TIMEOUT}s 内未完成）"
            )
        except (FileNotFoundError, OSError) as exc:
            return StepResult.fail_result(f"无法执行 npm install: {exc}")
        if inst.returncode != 0:
            return StepResult.fail_result(
                f"npm install 失败（退出码 {inst.returncode}）:\n{_output(inst)}"
            )
        logs.append("npm install 完成")

    # 2) npm run build:app
    try:
        build = _run(
            [_npm_cmd(), "run", "build:app", "--", "--mode", "production"],
            timeout=PACK_TIMEOUT,
            cwd=repo_dir,
            encoding=NPM_ENCODING,
        )
    except subprocess.TimeoutExpired:
        return StepResult.fail_result(
            f"npm run build:app 超时（{PACK_TIMEOUT}s 内未完成）"
        )
    except (FileNotFoundError, OSError) as exc:
        return StepResult.fail_result(f"无法执行 npm: {exc}")

    logs.append("npm run build:app 输出（末 40 行）:\n" + "\n".join(_output(build).splitlines()[-40:]))
    if build.returncode != 0:
        return StepResult.fail_result(
            f"npm run build:app 失败（退出码 {build.returncode}）:\n{_output(build)}"
        )

    # 3) 归一化 manifest + 复制就位（如 build:app 已内嵌则跳过，否则显式跑一次）
    if norm_script is not None:
        try:
            norm = _run(
                [_node_cmd(), norm_script, *norm_args],
                timeout=600,
                cwd=repo_dir,
                encoding=NPM_ENCODING,
            )
        except subprocess.TimeoutExpired:
            return StepResult.fail_result("manifest 归一化 + 资源就位超时")
        except (FileNotFoundError, OSError) as exc:
            return StepResult.fail_result(f"执行 manifest 归一化脚本失败: {exc}")

        logs.append("manifest 归一化 + 就位输出:\n" + _output(norm))
        if norm.returncode != 0:
            return StepResult.fail_result(
                f"manifest 归一化 + 资源就位失败（退出码 {norm.returncode}）:\n{_output(norm)}"
            )

    # 4) 新鲜度校验（和 HBuilderX 模式保持同样的"资源确实更新了"判定）
    min_mtime = max(old_mtime, pack_start - 2)
    deadline = time.time() + FRESHNESS_WAIT_TIMEOUT
    fresh = False
    while time.time() < deadline:
        if (
            os.path.isfile(final_manifest)
            and os.path.getmtime(final_manifest) >= min_mtime
        ):
            fresh = True
            break
        time.sleep(FRESHNESS_POLL_INTERVAL)
    if not fresh:
        return StepResult.fail_result(
            f"npm run build:app 成功，但等待 {FRESHNESS_WAIT_TIMEOUT}s 后 {final_manifest} 仍未更新（脚本可能未复制）:\n"
            + "\n".join(logs)
        )

    return StepResult.ok_result(
        "\n".join(logs) + f"\n本地打包资源已就位: {resources_dir}",
        resources_dir=resources_dir,
    )


def _run_hbuilderx_cli_mode(cfg):
    """原有 HBuilderX CLI 流程（作为 npm 不可用的兜底）。"""
    cli_path = cfg["hbuilderx"]["cli_path"]
    project_name = cfg["hbuilderx"]["project_name"]
    repo_dir = cfg["git"]["repo_dir"]

    if not os.path.isfile(cli_path):
        return StepResult.fail_result(f"HBuilderX cli文件不存在: {cli_path}")

    try:
        open_proc = _run(
            cli_path, ["project", "open", "--path", repo_dir], OPEN_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return StepResult.fail_result(
            f"HBuilderX打开项目超时（{OPEN_TIMEOUT}秒内未完成）"
        )
    except (FileNotFoundError, OSError) as exc:
        return StepResult.fail_result(f"无法执行HBuilderX cli {cli_path}: {exc}")
    if open_proc.returncode != 0:
        return StepResult.fail_result(
            f"HBuilderX打开项目失败（退出码 {open_proc.returncode}）:\n{_output(open_proc)}"
        )

    resources_dir = repo_resources_dir(cfg)
    manifest_path = os.path.join(resources_dir, "www", "manifest.json")
    old_mtime = (
        os.path.getmtime(manifest_path) if os.path.isfile(manifest_path) else 0.0
    )
    pack_start = time.time()

    try:
        pack_proc = _run(
            cli_path,
            [
                "publish",
                "--platform",
                "APP",
                "--type",
                "appResource",
                "--project",
                project_name,
            ],
            PACK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return StepResult.fail_result(
            f"HBuilderX本地打包超时（{PACK_TIMEOUT}秒内未完成）"
        )
    except (FileNotFoundError, OSError) as exc:
        return StepResult.fail_result(f"无法执行HBuilderX cli {cli_path}: {exc}")

    cli_output = _output(pack_proc)
    if pack_proc.returncode != 0:
        return StepResult.fail_result(
            f"HBuilderX打包失败（退出码 {pack_proc.returncode}）:\n{cli_output}"
        )

    min_mtime = max(old_mtime, pack_start - 2)
    deadline = time.time() + FRESHNESS_WAIT_TIMEOUT
    fresh = False
    while time.time() < deadline:
        if (
            os.path.isfile(manifest_path)
            and os.path.getmtime(manifest_path) >= min_mtime
        ):
            fresh = True
            break
        time.sleep(FRESHNESS_POLL_INTERVAL)
    if not fresh:
        return StepResult.fail_result(
            f"HBuilderX退出码为0但等待{FRESHNESS_WAIT_TIMEOUT}秒后本地打包资源仍未更新"
            "（打包可能被跳过，请确认HBuilderX主程序已启动、项目名正确）:\n" + cli_output
        )

    return StepResult.ok_result(
        f"打包方式：HBuilderX CLI\nHBuilderX打包完成，本地打包资源已生成: {resources_dir}\n{cli_output}",
        resources_dir=resources_dir,
    )


def run(cfg):
    try:
        repo_dir = cfg["git"]["repo_dir"]
        if not os.path.isdir(repo_dir):
            return StepResult.fail_result(f"仓库目录不存在: {repo_dir}")

        # 优先 npm：仓库是 Vite 式 uni-app 且带有 build:app 脚本
        if _package_has_build_app(repo_dir):
            return _run_npm_mode(cfg)

        # 兜底：HBuilderX CLI（只支持 Win/macOS）
        if not (sys.platform.startswith("win") or sys.platform.startswith("darwin")):
            return StepResult.fail_result(
                f"当前平台 {sys.platform} 不支持 HBuilderX 本地打包：HBuilderX 主程序仅提供 Windows / macOS 版本。"
                "请在 Windows 或 macOS 机器运行本流水线，或切换到 npm 模式（给仓库 package.json 增加 build:app 脚本：uni build -p app）。"
            )
        return _run_hbuilderx_cli_mode(cfg)
    except Exception as exc:
        return StepResult.fail_result(f"资源打包步骤执行异常: {exc}")
