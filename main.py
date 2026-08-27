import argparse
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


def run_web(project_dir: str, config_path: str, host: str, port: int) -> None:
    from web.app import create_app

    app = create_app(project_dir=project_dir, config_path=config_path)
    app.run(host=host, port=port, threaded=True)


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

    if is_frozen() and args.config == "config.yaml":
        args.config = os.path.join(app_root_dir(), "config.yaml")

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
        print("仅启动飞书机器人，Web 控制台未启动")
        print("飞书机器人启动中，等待触发关键词…")
        print("已配置的项目:")
        print(projects_summary(cfg))
        from bot.feishu_bot import FeishuBot

        FeishuBot(cfg).start()
        return 0

    print("Web 控制台与飞书机器人双服务启动中…")
    print(f"Web控制台: http://{args.host}:{args.port}")
    web_thread = threading.Thread(
        target=run_web,
        args=(project_dir, config_path, args.host, args.port),
        daemon=True,
    )
    web_thread.start()
    print("飞书机器人启动中，等待触发关键词…")
    print("已配置的项目:")
    print(projects_summary(cfg))
    from bot.feishu_bot import FeishuBot

    FeishuBot(cfg).start()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
