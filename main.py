import argparse
import io
import os
import shutil
import sys
import threading

from pipeline.common import app_root_dir
from pipeline.common import is_frozen
from pipeline.config import ConfigError
from pipeline.config import default_project
from pipeline.config import load_config
from pipeline.config import projects_summary
from pipeline.config import select_project
from pipeline.runner import run_pipeline


def _configure_io() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def run_web(project_dir: str, config_path: str, host: str, port: int) -> None:
    from web.app import create_app

    app = create_app(project_dir=project_dir, config_path=config_path)
    app.run(host=host, port=port, threaded=True)


def feishu_enabled(cfg) -> bool:
    """Return True when the user has configured a real Feishu app_id/app_secret.

    The validation layer (pipeline.config._feishu_enabled + validate_config) treats
    empty credentials / the default ``cli_xxxxxxxxxxxxxxxx`` placeholder as
    "Feishu disabled", which lets first-time users launch the exe into Web-only mode
    immediately. Delegate to that helper to keep the rule in one place.
    """
    from pipeline.config import _feishu_enabled
    return bool(_feishu_enabled(cfg))


def start_feishu_bot(cfg, bot_only: bool) -> None:
    """Start the Feishu long-connection bot with graceful error handling.

    - Raises on critical startup errors *only* when running in --bot-only mode
      (the user explicitly asked for Feishu, so failing hard is correct).
    - In dual-service mode, prints a clear banner and lets the Web console keep
      serving, instead of crashing the entire process.
    """
    from bot.feishu_bot import FeishuBot

    bot = FeishuBot(cfg)
    # Redirect noisy SDK log lines to stderr so they don't interrupt our banner
    # in combined stdout captures (e.g. from tests / exe launch wrappers).
    import logging
    for _logger_name in ("Lark", "lark_oapi"):
        _lg = logging.getLogger(_logger_name)
        if _lg.handlers:
            for _h in list(_lg.handlers):
                try:
                    import sys
                    _h.setStream(sys.stderr)
                except Exception:
                    pass
    try:
        bot.start()
    except Exception as exc:
        # Try to extract a short, human-readable message; lark_oapi usually attaches
        # something like "1000040346: app_id is invalid".
        msg = str(exc).strip() or exc.__class__.__name__
        print()
        print("============================================================")
        print("  飞书机器人启动失败")
        print("============================================================")
        print(f"  原因: {msg}")
        # Common codes we can give actionable hints for
        if "1000040346" in msg or "app_id is invalid" in msg.lower():
            print("  提示: 飞书 app_id / app_secret 无效。")
            print("        - 在 config.yaml 的 feishu.app_id / feishu.app_secret 填入真实凭证。")
            print("        - 若暂时不需要飞书，请把飞书凭证留空或直接删除 feishu 配置块，再运行一次。")
        elif "401" in msg or "403" in msg or "auth" in msg.lower() or "token" in msg.lower():
            print("  提示: 鉴权失败。请检查 app_secret 是否正确、应用是否已发布版本并授予机器人/消息权限。")
        elif "timed out" in msg.lower() or "connect" in msg.lower():
            print("  提示: 连接飞书服务器失败。检查网络（能访问 msg-frontier.feishu.cn）、代理设置、防火墙。")
        print("============================================================")
        if bot_only:
            print("当前为 --bot-only 模式，飞书不可用即无法继续运行，程序退出。")
            raise
        print("Web 控制台仍可正常使用（http://127.0.0.1:8000）。")
        print("============================================================")
        return


def _resolve_default_config_path(cli_default: str) -> str:
    """Resolve the ``config.yaml`` location.

    Order of precedence:

    1. The path passed via ``--config`` on the command line (caller handled that).
    2. When running in a Docker container, prefer the bind-mounted read-only
       config directory at ``/app/runtime-config/config.yaml``
       (see docker-compose.yml volume BUILDER_CONFIG_DIR).
    3. Frozen binary (PyInstaller): next to the extracted/frozen app.
    4. Otherwise fall back to ``./config.yaml`` relative to the working directory.
    """
    if cli_default != "config.yaml":
        return cli_default
    docker_mounted = "/app/runtime-config/config.yaml"
    if os.path.isfile(docker_mounted):
        return docker_mounted
    if is_frozen():
        return os.path.join(app_root_dir(), "config.yaml")
    return "config.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="uni-app Android 自动构建打包流水线")
    parser.add_argument("--run-once", action="store_true", help="直接运行一次流水线后退出")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径，默认 config.yaml")
    parser.add_argument("--project", help="要构建的项目 key/名称/触发词，多项目时必须指定")
    parser.add_argument("--list", action="store_true", help="列出配置中的所有项目后退出")
    parser.add_argument("--web-only", action="store_true", help="只启动 Web 控制台，不启动飞书机器人")
    parser.add_argument("--bot-only", action="store_true", help="只启动飞书机器人，不启动 Web 控制台")
    parser.add_argument("--host", default="127.0.0.1", help="Web 服务监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="Web 服务监听端口，默认 8000")
    args = parser.parse_args()

    if is_frozen() and sys.platform not in ("win32", "darwin"):
        print("提示: 当前为二进制打包版本且运行在 Linux 服务器；git/android/kodcloud 可正常执行，但 HBuilderX 步骤必须要求 Windows/macOS 的 HBuilderX 主程序。")

    args.config = _resolve_default_config_path(args.config)

    if not os.path.isfile(args.config):
        example_path = os.path.join(os.path.dirname(os.path.abspath(args.config)), "config.yaml.example")
        if os.path.isfile(example_path):
            shutil.copyfile(example_path, args.config)
            print(f"首次运行: 已自动生成配置模板 {os.path.abspath(args.config)}")
            print("请填写配置内容后重新运行本程序")
            return 2

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"配置错误: {exc}")
        return 1

    if args.list:
        print("已配置的项目:")
        print(projects_summary(cfg))
        return 0

    if args.run_once:
        if args.project:
            project = select_project(cfg, args.project)
            if project is None:
                print(f"未找到项目: {args.project}")
                print("可选项目:")
                print(projects_summary(cfg))
                return 1
        else:
            project = default_project(cfg)
            if project is None:
                print("配置了多个项目，请用 --project 指定要构建的项目:")
                print(projects_summary(cfg))
                return 1
        report = run_pipeline(cfg, project)
        print(report.text_summary())
        return 0 if report.success else 1

    config_path = os.path.abspath(args.config)
    project_dir = os.path.dirname(config_path)

    if args.web_only:
        print(f"Web服务启动中: http://{args.host}:{args.port}")
        run_web(project_dir, config_path, args.host, args.port)
        return 0

    if args.bot_only:
        if not feishu_enabled(cfg):
            print("未启用飞书机器人（feishu.app_id/app_secret 留空或为占位值），--bot-only 模式无法继续。请先填写或改用 --web-only。")
            return 2
        print("仅启动飞书机器人，Web 控制台未启动")
        print("飞书机器人启动中，等待触发关键词…")
        print("已配置的项目:")
        print(projects_summary(cfg))
        start_feishu_bot(cfg, bot_only=True)
        return 0

    print("Web 控制台与飞书机器人双服务启动中…")
    print(f"Web控制台: http://{args.host}:{args.port}")
    web_thread = threading.Thread(
        target=run_web,
        args=(project_dir, config_path, args.host, args.port),
        daemon=True,
    )
    web_thread.start()
    if feishu_enabled(cfg):
        print("飞书机器人启动中，等待触发关键词…")
        print("已配置的项目:")
        print(projects_summary(cfg))
        start_feishu_bot(cfg, bot_only=False)
    else:
        print("飞书机器人已跳过（feishu.app_id/app_secret 留空或为占位值；仅运行 Web 控制台）。")
        print("如需启用飞书：填写 config.yaml 的 feishu.app_id / feishu.app_secret 后重启。")
        web_thread.join()
    return 0


if __name__ == "__main__":
    _configure_io()
    print(f"平台诊断: platform={sys.platform}, python={sys.version.split()[0]}, encoding(stdout)={getattr(sys.stdout,'encoding','?')}")
    sys.exit(main())
