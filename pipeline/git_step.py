import os
import subprocess

from .common import StepResult

DEFAULT_TIMEOUT = 120
PULL_TIMEOUT = 300
MAX_COMMITS_SHOWN = 15
LATEST_COMMITS_SHOWN = 3


def _git(args, cwd, timeout=DEFAULT_TIMEOUT):
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _output(proc):
    parts = [proc.stdout or "", proc.stderr or ""]
    return "\n".join(part.strip() for part in parts if part.strip())


def run(cfg):
    try:
        repo_dir = cfg["git"]["repo_dir"]
        branch = cfg["git"]["branch"]
        if not os.path.isdir(repo_dir):
            return StepResult.fail_result(f"git仓库目录不存在: {repo_dir}")

        try:
            check = _git(["rev-parse", "--git-dir"], repo_dir)
        except subprocess.TimeoutExpired:
            return StepResult.fail_result("校验git仓库超时")
        except FileNotFoundError:
            return StepResult.fail_result("未找到git命令，请确认已安装Git并加入系统PATH")
        if check.returncode != 0:
            return StepResult.fail_result(
                f"目录 {repo_dir} 不是有效的git仓库: {_output(check)}"
            )

        try:
            current = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir)
        except subprocess.TimeoutExpired:
            return StepResult.fail_result("查询当前分支超时")
        if current.returncode != 0:
            return StepResult.fail_result(f"查询当前分支失败: {_output(current)}")

        current_branch = (current.stdout or "").strip()
        logs = [f"当前分支: {current_branch}, 目标分支: {branch}"]
        if current_branch != branch:
            try:
                checkout = _git(["checkout", branch], repo_dir)
            except subprocess.TimeoutExpired:
                return StepResult.fail_result(f"切换分支 {branch} 超时")
            if checkout.returncode != 0:
                return StepResult.fail_result(
                    f"切换分支 {branch} 失败: {_output(checkout)}"
                )
            logs.append(f"已从 {current_branch} 切换到 {branch}")

        try:
            old_head_proc = _git(["rev-parse", "HEAD"], repo_dir)
            old_head = (
                (old_head_proc.stdout or "").strip()
                if old_head_proc.returncode == 0
                else None
            )
        except subprocess.TimeoutExpired:
            old_head = None

        try:
            pull = _git(["pull"], repo_dir, timeout=PULL_TIMEOUT)
        except subprocess.TimeoutExpired:
            return StepResult.fail_result(f"git pull超时（{PULL_TIMEOUT}秒内未完成）")
        if pull.returncode != 0:
            return StepResult.fail_result(
                f"git pull失败（退出码 {pull.returncode}）:\n{_output(pull)}"
            )
        logs.append(f"git pull完成:\n{_output(pull) or '无输出'}")

        update_log, commit_count = _collect_updates(repo_dir, old_head)
        if update_log:
            logs.append(update_log)
        return StepResult.ok_result(
            "\n".join(logs),
            repo_dir=repo_dir,
            branch=branch,
            update_log=update_log,
            commit_count=commit_count,
        )
    except Exception as exc:
        return StepResult.fail_result(f"git步骤执行异常: {exc}")


def _collect_updates(repo_dir, old_head):
    latest_block = _latest_commits(repo_dir)
    if not old_head:
        return "", 0
    try:
        new_head_proc = _git(["rev-parse", "HEAD"], repo_dir)
    except subprocess.TimeoutExpired:
        return "", 0
    if new_head_proc.returncode != 0:
        return "", 0
    new_head = (new_head_proc.stdout or "").strip()
    if not new_head or new_head == old_head:
        parts = ["📝 本次更新: 无新提交（代码与上次构建一致）"]
        if latest_block:
            parts.append(latest_block)
        return "\n".join(parts), 0
    try:
        log_proc = _git(
            [
                "log",
                "--reverse",
                "--pretty=format:%h %an %ad %s",
                "--date=format:%m-%d %H:%M",
                f"{old_head}..{new_head}",
            ],
            repo_dir,
        )
    except subprocess.TimeoutExpired:
        return "", 0
    if log_proc.returncode != 0:
        return "", 0
    lines = [ln.strip() for ln in (log_proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        parts = ["📝 本次更新: 无新提交（代码与上次构建一致）"]
        if latest_block:
            parts.append(latest_block)
        return "\n".join(parts), 0
    shown = lines[-MAX_COMMITS_SHOWN:]
    extra = len(lines) - len(shown)
    body = "\n".join(shown)
    if extra > 0:
        body += f"\n…另有 {extra} 个较早提交未显示"
    parts = [f"📝 本次更新（{len(lines)}个提交）:\n{body}"]
    if latest_block:
        parts.append(latest_block)
    return "\n".join(parts), len(lines)


def _latest_commits(repo_dir):
    try:
        proc = _git(
            [
                "log",
                f"-{LATEST_COMMITS_SHOWN}",
                "--pretty=format:%h %an %ad %s",
                "--date=format:%m-%d %H:%M",
            ],
            repo_dir,
        )
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        return ""
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    return f"📌 最近{len(lines)}次提交:\n" + "\n".join(lines)
