import os
import subprocess
import time

from .common import StepResult
from .config import repo_resources_dir

OPEN_TIMEOUT = 300
PACK_TIMEOUT = 900
FRESHNESS_WAIT_TIMEOUT = 90
FRESHNESS_POLL_INTERVAL = 2


def _run_cli(cli_path, args, timeout):
    return subprocess.run(
        [cli_path] + args,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
        timeout=timeout,
    )


def _output(proc):
    parts = [proc.stdout or "", proc.stderr or ""]
    return "\n".join(part.strip() for part in parts if part.strip())


def run(cfg):
    try:
        cli_path = cfg["hbuilderx"]["cli_path"]
        project_name = cfg["hbuilderx"]["project_name"]
        repo_dir = cfg["git"]["repo_dir"]

        if not os.path.isfile(cli_path):
            return StepResult.fail_result(f"HBuilderX cli文件不存在: {cli_path}")

        try:
            open_proc = _run_cli(
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
            pack_proc = _run_cli(
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
            if os.path.isfile(manifest_path) and os.path.getmtime(manifest_path) >= min_mtime:
                fresh = True
                break
            time.sleep(FRESHNESS_POLL_INTERVAL)
        if not fresh:
            return StepResult.fail_result(
                f"HBuilderX退出码为0但等待{FRESHNESS_WAIT_TIMEOUT}秒后本地打包资源仍未更新"
                "（打包可能被跳过，请确认HBuilderX主程序已启动、项目名正确）:\n" + cli_output
            )

        return StepResult.ok_result(
            f"HBuilderX打包完成，本地打包资源已生成: {resources_dir}\n{cli_output}",
            resources_dir=resources_dir,
        )
    except Exception as exc:
        return StepResult.fail_result(f"HBuilderX打包步骤执行异常: {exc}")
