import os
import re
import secrets
import sys
import time
from datetime import datetime

import yaml
from flask import Flask
from flask import flash
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for

from pipeline.build_manager import build_manager
from pipeline.config import ConfigError
from pipeline.config import load_config
from pipeline.config import select_project
from pipeline.config import validate_config
from pipeline.runner import run_pipeline

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

WEB_DIR = os.path.dirname(os.path.abspath(__file__))


def _split_text(raw) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[\n\r,，;；]", str(raw)) if part.strip()]


def _assemble_cfg(form) -> dict:
    cfg = {
        "feishu": {
            "app_id": (form.get("feishu[app_id]") or "").strip(),
            "app_secret": form.get("feishu[app_secret]") or "",
            "trigger_keywords": _split_text(form.get("feishu[trigger_keywords]")),
        }
    }
    default_project = (form.get("default_project") or "").strip()
    if default_project:
        cfg["default_project"] = default_project
    projects = []
    index = 0
    while form.get(f"projects[{index}][key]") is not None:
        projects.append(
            {
                "key": (form.get(f"projects[{index}][key]") or "").strip(),
                "name": (form.get(f"projects[{index}][name]") or "").strip(),
                "aliases": _split_text(form.get(f"projects[{index}][aliases]")),
                "git": {
                    "repo_dir": (form.get(f"projects[{index}][git][repo_dir]") or "").strip(),
                    "branch": (form.get(f"projects[{index}][git][branch]") or "").strip(),
                },
                "hbuilderx": {
                    "cli_path": (form.get(f"projects[{index}][hbuilderx][cli_path]") or "").strip(),
                    "project_name": (form.get(f"projects[{index}][hbuilderx][project_name]") or "").strip(),
                    "appid": (form.get(f"projects[{index}][hbuilderx][appid]") or "").strip(),
                },
                "android": {
                    "project_dir": (form.get(f"projects[{index}][android][project_dir]") or "").strip(),
                    "assets_dir": (form.get(f"projects[{index}][android][assets_dir]") or "").strip(),
                    "apk_output": (form.get(f"projects[{index}][android][apk_output]") or "").strip(),
                },
                "kodcloud": {
                    "webdav_url": (form.get(f"projects[{index}][kodcloud][webdav_url]") or "").strip(),
                    "username": (form.get(f"projects[{index}][kodcloud][username]") or "").strip(),
                    "password": form.get(f"projects[{index}][kodcloud][password]") or "",
                    "remote_dir": (form.get(f"projects[{index}][kodcloud][remote_dir]") or "").strip(),
                    "apk_prefix": (form.get(f"projects[{index}][kodcloud][apk_prefix]") or "").strip(),
                },
            }
        )
        index += 1
    cfg["projects"] = projects
    return cfg


def _recent_builds(log_dir: str, limit: int = 5) -> list[dict]:
    try:
        names = os.listdir(log_dir)
    except OSError:
        names = []
    entries = []
    for name in names:
        if not (name.startswith("build_") and name.endswith(".log")):
            continue
        try:
            mtime = os.path.getmtime(os.path.join(log_dir, name))
        except OSError:
            continue
        entries.append((mtime, name))
    entries.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "name": name,
            "time": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for mtime, name in entries[:limit]
    ]


def _human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(num)} B"


def create_app(
    project_dir: str | None = None,
    cfg: dict | None = None,
    config_path: str | None = None,
) -> Flask:
    if project_dir is None:
        project_dir = ROOT_DIR
    project_dir = os.path.abspath(project_dir)
    if config_path is None:
        config_path = os.path.join(project_dir, "config.yaml")
    else:
        config_path = os.path.abspath(config_path)
    if cfg is None:
        cfg = load_config(config_path)

    app = Flask(
        __name__,
        template_folder=os.path.join(WEB_DIR, "templates"),
        static_folder=os.path.join(WEB_DIR, "static"),
    )
    app.config["SECRET_KEY"] = secrets.token_hex(16)
    app.config["BUILD_CFG"] = cfg
    app.config["BUILD_PROJECT_DIR"] = project_dir
    app.config["BUILD_CONFIG_PATH"] = config_path

    @app.route("/")
    def index():
        cfg = app.config["BUILD_CFG"]
        default_key = (cfg.get("default_project") or "").strip()
        projects = []
        for project in cfg.get("projects", []):
            key = str(project.get("key", "")).strip()
            projects.append(
                {
                    "key": key,
                    "name": str(project.get("name", "")).strip(),
                    "aliases": "、".join(str(a) for a in (project.get("aliases") or [])),
                    "is_default": key == default_key,
                }
            )
        current_job = build_manager.current_job()
        return render_template(
            "index.html",
            projects=projects,
            is_busy=build_manager.is_busy(),
            current_project_name=current_job["project_name"] if current_job else None,
            current_job_id=current_job["job_id"] if current_job else None,
            recent_builds=_recent_builds(os.path.join(app.config["BUILD_PROJECT_DIR"], "logs")),
        )

    @app.get("/logs")
    def logs_list():
        log_dir = os.path.join(app.config["BUILD_PROJECT_DIR"], "logs")
        raw = []
        try:
            names = os.listdir(log_dir)
        except OSError:
            names = []
        for name in names:
            if not name.endswith(".log"):
                continue
            path = os.path.join(log_dir, name)
            try:
                if not os.path.isfile(path):
                    continue
                mtime = os.path.getmtime(path)
                size = os.path.getsize(path)
            except OSError:
                continue
            raw.append((mtime, name, size))
        raw.sort(key=lambda item: item[0], reverse=True)
        logs = [
            {
                "filename": name,
                "size": _human_size(size),
                "mtime": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for mtime, name, size in raw
        ]
        return render_template("logs.html", logs=logs)

    @app.get("/logs/<filename>")
    def log_view(filename):
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or ".." in filename
            or os.path.basename(filename) != filename
        ):
            return "", 404
        path = os.path.join(app.config["BUILD_PROJECT_DIR"], "logs", filename)
        if not os.path.isfile(path):
            return "", 404
        with open(path, "r", encoding="utf-8", errors="replace") as fp:
            content = fp.read()
        return render_template("log_view.html", filename=filename, content=content)

    @app.get("/config")
    def config_page():
        cfg = app.config["BUILD_CFG"]
        config_path = app.config["BUILD_CONFIG_PATH"]
        error = request.args.get("error")
        return render_template("config.html", cfg=cfg, config_path=config_path, error=error)

    @app.post("/config")
    def config_save():
        cfg = _assemble_cfg(request.form)
        try:
            validate_config(cfg)
        except ConfigError as exc:
            flash(str(exc), "error")
            return redirect(url_for("config_page"))
        config_path = app.config["BUILD_CONFIG_PATH"]
        backup_path = config_path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(config_path, "rb") as src:
            original = src.read()
        with open(backup_path, "wb") as dst:
            dst.write(original)
        tmp_path = config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False))
        os.replace(tmp_path, config_path)
        app.config["BUILD_CFG"] = cfg
        flash("已保存并生效，原配置已自动备份", "success")
        return redirect(url_for("config_page"))

    @app.post("/build/<key>")
    def trigger_build(key):
        cfg = app.config["BUILD_CFG"]
        project = select_project(cfg, key)
        if project is None:
            return jsonify({"ok": False, "reason": f"未找到项目: {key}"}), 200
        if build_manager.is_busy():
            return jsonify({"ok": False, "reason": "构建进行中"}), 200
        project_key = str(project.get("key", ""))
        project_name = str(project.get("name", "")).strip()
        project_dir = app.config["BUILD_PROJECT_DIR"]
        job_id_box = [None]

        def build_fn():
            time.sleep(0)
            latest_cfg = load_config(app.config["BUILD_CONFIG_PATH"])
            target = select_project(latest_cfg, project_key)
            if target is None:
                raise ConfigError(f"配置中未找到项目: {project_key}")

            def progress(report, running_step):
                job_id = job_id_box and job_id_box[0]
                if job_id:
                    build_manager.set_running_step(job_id, running_step)
                    build_manager.set_report(job_id, report)

            return run_pipeline(latest_cfg, target, on_progress=progress)

        job_id = build_manager.trigger(project_key, project_name, build_fn)
        if job_id is None:
            return jsonify({"ok": False, "reason": "构建进行中"}), 200
        job_id_box[0] = job_id
        return jsonify({"ok": True, "job_id": job_id}), 200

    @app.get("/build/<job_id>")
    def job_status(job_id):
        job = build_manager.get_job(job_id)
        if job is None:
            return jsonify({"ok": False, "reason": "任务不存在"}), 200
        busy = bool(job["busy"])
        report = job.get("report")
        running_step = job.get("running_step")
        final = None
        if not busy and job.get("result") is not None:
            result = job["result"]
            final = result if isinstance(result, str) else result.text_summary()
        return (
            jsonify(
                {
                    "ok": True,
                    "busy": busy,
                    "project_name": job.get("project_name"),
                    "running_step": running_step,
                    "summary": report.progress_summary(running_step) if report is not None else None,
                    "final": final,
                }
            ),
            200,
        )

    return app