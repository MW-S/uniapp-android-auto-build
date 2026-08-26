import os
import shutil
import stat
import sys

from .common import StepResult
from .config import repo_resources_dir


def _on_rmtree_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _clear_target(target):
    if os.path.isfile(target):
        os.remove(target)
        return
    if not os.path.isdir(target):
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=_on_rmtree_error)
    else:
        shutil.rmtree(target, onerror=_on_rmtree_error)


def run(cfg):
    try:
        source = repo_resources_dir(cfg)
        if not os.path.isdir(source):
            return StepResult.fail_result(
                f"本地打包资源目录不存在: {source}，请先执行HBuilderX打包"
            )

        project_dir = cfg["android"]["project_dir"]
        assets_dir = cfg["android"]["assets_dir"]
        if os.path.isabs(assets_dir):
            target = assets_dir
        else:
            target = os.path.abspath(os.path.join(project_dir, assets_dir))

        try:
            _clear_target(target)
        except Exception as exc:
            return StepResult.fail_result(f"清空目标目录失败 {target}: {exc}")

        try:
            shutil.copytree(source, target)
        except Exception as exc:
            return StepResult.fail_result(f"复制资源失败 {source} -> {target}: {exc}")

        manifest_path = os.path.join(target, "www", "manifest.json")
        if not os.path.isfile(manifest_path):
            return StepResult.fail_result(
                f"复制后的资源不完整，缺少 www/manifest.json: {manifest_path}"
            )

        return StepResult.ok_result(
            f"资源复制完成，目标目录: {target}", target_dir=target
        )
    except Exception as exc:
        return StepResult.fail_result(f"资源复制步骤执行异常: {exc}")
