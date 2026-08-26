import os
import time
import traceback
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime

from pipeline import android_build_step
from pipeline import copy_resources_step
from pipeline import git_step
from pipeline import hbuilderx_step
from pipeline import kodcloud_upload_step
from pipeline.common import StepResult
from pipeline.config import ConfigError
from pipeline.config import default_project

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT_DIR, "logs")

STEP_GIT = "git更新代码"
STEP_HBUILDERX = "HBuilderX资源打包"
STEP_COPY = "资源清理与复制"
STEP_ANDROID = "Android签名构建"
STEP_UPLOAD = "kodcloud上传"

FULL_LOG_MAX_CHARS = 15000
STEP_LOG_LINE_LIMIT = 80


@dataclass
class StepReport:
    name: str
    ok: bool
    log: str
    duration: float


@dataclass
class PipelineReport:
    success: bool = False
    project_name: str = ""
    steps: list[StepReport] = field(default_factory=list)
    failed_step: str | None = None
    apk_path: str | None = None
    apk_name: str | None = None
    apk_size: int | None = None
    total_duration: float = 0.0
    log_file: str | None = None
    update_log: str = ""
    started_at: float = 0.0
    full_log: str = ""

    def progress_summary(self, running_step: str | None = None) -> str:
        lines = [f"🚦 正在构建【{self.project_name}】"]
        for step in self.steps:
            mark = "✔" if step.ok else "✘"
            lines.append(f"[{mark}] {step.name} ({step.duration:.1f}s)")
            if step.ok:
                tail = next((ln for ln in reversed(step.log.splitlines()) if ln.strip()), "")
                if len(tail) > STEP_LOG_LINE_LIMIT:
                    tail = tail[:STEP_LOG_LINE_LIMIT] + "…"
                lines.append(f"  ↳ {tail}")
        if running_step and not any(s.name == running_step for s in self.steps):
            lines.append(f"[⏳] {running_step} 进行中…")
        if self.update_log:
            lines.append(self.update_log)
        if self.started_at:
            elapsed = int(time.time() - self.started_at)
            lines.append(f"已耗时: {elapsed // 60}分{elapsed % 60}秒")
        return "\n".join(lines)

    def text_summary(self) -> str:
        title = "✅ 构建成功" if self.success else "❌ 构建失败"
        if self.project_name:
            title = f"{title}【{self.project_name}】"
        lines = [title]
        for step in self.steps:
            mark = "✔" if step.ok else "✘"
            lines.append(f"[{mark}] {step.name} ({step.duration:.1f}s)")
        if self.update_log:
            lines.append(self.update_log)
        if not self.success:
            if self.failed_step:
                lines.append(f"失败步骤: {self.failed_step}")
                failed = next((s for s in self.steps if s.name == self.failed_step), None)
                if failed is not None:
                    tail = failed.log.splitlines()[-10:]
                    lines.extend(tail)
        else:
            if self.apk_name:
                size_mb = (self.apk_size or 0) / (1024 * 1024)
                lines.append(f"APK: {self.apk_name} ({size_mb:.2f}MB)")
            upload = next((s for s in self.steps if s.name == STEP_UPLOAD), None)
            if upload is not None:
                upload_lines = [ln for ln in upload.log.splitlines() if ln.strip()]
                if upload_lines:
                    lines.append(upload_lines[-1])
        minutes = int(self.total_duration // 60)
        seconds = int(self.total_duration % 60)
        lines.append(f"总耗时: {minutes}分{seconds}秒")
        if self.full_log:
            lines.append("")
            lines.append("📄 完整日志:")
            n = len(self.full_log)
            if n > FULL_LOG_MAX_CHARS:
                lines.append(self.full_log[:FULL_LOG_MAX_CHARS] + f"…已截断，共{n}字符，完整日志见 {self.log_file or ''}")
            else:
                lines.append(self.full_log)
        return "\n".join(lines)


def _open_log_file(report: PipelineReport, project_key: str):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_key = "".join(ch for ch in project_key if ch.isalnum() or ch in "-_") or "project"
        log_path = os.path.join(LOG_DIR, f"build_{safe_key}_{stamp}.log")
        fp = open(log_path, "a", encoding="utf-8")
        report.log_file = log_path
        return fp
    except Exception:
        return None


def run_pipeline(cfg: dict, project: dict | None = None, on_progress=None) -> PipelineReport:
    if project is None:
        project = default_project(cfg)
    if project is None:
        raise ConfigError("配置了多个项目且未指定 default_project，请明确指定要构建的项目")
    report = PipelineReport(project_name=str(project.get("name", "")).strip())
    report.started_at = time.time()
    pipeline_start = time.perf_counter()
    log_fp = _open_log_file(report, str(project.get("key", "")))

    def notify(running_step: str | None) -> None:
        if on_progress is None:
            return
        try:
            on_progress(report, running_step)
        except Exception:
            pass

    def write_log(text: str) -> None:
        if log_fp is None:
            return
        try:
            log_fp.write(text + "\n")
            log_fp.flush()
        except Exception:
            pass

    def execute(name: str, func) -> StepResult:
        notify(name)
        write_log("=" * 60)
        write_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 步骤开始: {name}")
        step_start = time.perf_counter()
        try:
            result = func()
            if not isinstance(result, StepResult):
                result = StepResult(ok=False, log=f"步骤 {name} 返回了非法结果: {result!r}")
        except Exception:
            duration = time.perf_counter() - step_start
            result = StepResult(ok=False, log=traceback.format_exc())
            step_report = StepReport(name=name, ok=False, log=result.log, duration=duration)
            report.steps.append(step_report)
            report.failed_step = name
            write_log(result.log)
            write_log(f"步骤异常: {name} (耗时 {duration:.1f}s)")
            notify(None)
            return result
        duration = time.perf_counter() - step_start
        step_report = StepReport(name=name, ok=result.ok, log=result.log or "", duration=duration)
        report.steps.append(step_report)
        write_log(result.log or "")
        status = "成功" if result.ok else "失败"
        write_log(f"步骤{status}: {name} (耗时 {duration:.1f}s)")
        if not result.ok:
            report.failed_step = name
        notify(None)
        return result

    try:
        write_log(f"构建项目: {project.get('name')} (key={project.get('key')})")
        git_result = execute(STEP_GIT, lambda: git_step.run(project))
        if not git_result.ok:
            return report
        report.update_log = git_result.data.get("update_log") or ""
        hbuilderx_result = execute(STEP_HBUILDERX, lambda: hbuilderx_step.run(project))
        if not hbuilderx_result.ok:
            return report
        copy_result = execute(STEP_COPY, lambda: copy_resources_step.run(project))
        if not copy_result.ok:
            return report
        android_result = execute(STEP_ANDROID, lambda: android_build_step.run(project))
        if not android_result.ok:
            return report
        apk_path = android_result.data.get("apk_path")
        upload_result = execute(STEP_UPLOAD, lambda: kodcloud_upload_step.run(project, apk_path))
        if not upload_result.ok:
            return report
        report.success = True
        report.apk_path = apk_path
        report.apk_name = android_result.data.get("apk_name")
        report.apk_size = android_result.data.get("apk_size")
    except Exception:
        report.success = False
        if report.failed_step is None:
            report.failed_step = "未知"
        write_log(traceback.format_exc())
    finally:
        report.total_duration = time.perf_counter() - pipeline_start
        write_log("=" * 60)
        write_log(f"流水线结束: success={report.success}, failed_step={report.failed_step}")
        if log_fp is not None:
            try:
                log_fp.flush()
                with open(report.log_file, "r", encoding="utf-8") as log_reader:
                    report.full_log = log_reader.read()
            except Exception:
                pass
            try:
                log_fp.close()
            except Exception:
                pass
    return report
