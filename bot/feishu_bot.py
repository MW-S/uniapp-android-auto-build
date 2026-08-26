import json
import re

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.api.im.v1 import ReplyMessageRequest
from lark_oapi.api.im.v1 import ReplyMessageRequestBody
from lark_oapi.api.im.v1 import UpdateMessageRequest
from lark_oapi.api.im.v1 import UpdateMessageRequestBody

from pipeline.build_manager import build_manager
from pipeline.config import default_project
from pipeline.config import find_project
from pipeline.config import projects_summary
from pipeline.runner import run_pipeline

AT_PLACEHOLDER_PATTERN = re.compile(r"@_user_\d+")
SUMMARY_MAX_LEN = 20000


def parse_message_text(data: P2ImMessageReceiveV1) -> str | None:
    try:
        event = getattr(data, "event", None)
        message = getattr(event, "message", None) if event is not None else None
        if message is None or message.message_type != "text":
            return None
        content = json.loads(message.content or "{}")
        text = content.get("text")
        if text is None:
            return None
        return AT_PLACEHOLDER_PATTERN.sub("", text).strip()
    except Exception:
        return None


def match_keyword(text: str, keywords) -> bool:
    if not text:
        return False
    return any(kw and kw in text for kw in (keywords or []))


class FeishuBot:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        feishu_cfg = cfg.get("feishu", {}) or {}
        self.app_id = feishu_cfg.get("app_id", "")
        self.app_secret = feishu_cfg.get("app_secret", "")
        self.trigger_keywords = feishu_cfg.get("trigger_keywords") or []

    def start(self) -> None:
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        cli = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
        )
        cli.start()

    def _on_message(self, data: P2ImMessageReceiveV1) -> None:
        try:
            message = getattr(getattr(data, "event", None), "message", None)
            message_type = getattr(message, "message_type", None)
            text = parse_message_text(data)
            print(f"[收到消息] 类型={message_type}, 内容={text!r}")
            if text is None:
                return
            if not match_keyword(text, self.trigger_keywords):
                print("[收到消息] 未命中触发关键词，忽略")
                return
            message_id = data.event.message.message_id
            project = find_project(self.cfg, text)
            if project is None:
                project = default_project(self.cfg)
            if project is None:
                self._reply(
                    message_id,
                    "❓ 未识别到要构建的项目，请在消息中带上项目名称或触发词，例如“打包 pda”。\n"
                    "可选项目:\n" + projects_summary(self.cfg),
                )
                return
            placeholder_id = self._reply(message_id, "⏳ 收到指令，正在处理…")
            job_id_box = [None]

            def build_fn():
                job_id = job_id_box[0]
                self._update_status(
                    placeholder_id, f"🚦 正在构建【{project.get('name')}】…"
                )

                def progress(report, running_step):
                    if job_id:
                        build_manager.set_report(job_id, report)
                    self._update_status(
                        placeholder_id, report.progress_summary(running_step)
                    )

                try:
                    report = run_pipeline(self.cfg, project, on_progress=progress)
                    text = report.text_summary()
                    if len(text) > SUMMARY_MAX_LEN:
                        text = text[:SUMMARY_MAX_LEN]
                    self._update_status(placeholder_id, text)
                except Exception as exc:
                    print(f"构建任务异常: {exc}")
                    self._update_status(placeholder_id, f"❌ 构建异常: {exc}")

            job_id = build_manager.trigger(
                project["key"], project.get("name", ""), build_fn
            )
            if job_id is None:
                self._update_status(placeholder_id, "⏳ 构建进行中，请稍后再试")
                return
            job_id_box[0] = job_id
        except Exception as exc:
            print(f"消息处理异常: {exc}")

    def _client(self):
        return (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .build()
        )

    def _reply(self, message_id: str, text: str) -> str | None:
        try:
            req = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                .build()
            )
            resp = self._client().im.v1.message.reply(req)
            if not resp.success:
                print(f"飞书回复失败: code={resp.code}, msg={resp.msg}")
                return None
            if resp.data is not None:
                return getattr(resp.data, "message_id", None)
            return None
        except Exception as exc:
            print(f"飞书回复异常: {exc}")
            return None

    def _update_status(self, status_message_id: str, text: str) -> None:
        try:
            req = (
                UpdateMessageRequest.builder()
                .message_id(status_message_id)
                .request_body(
                    UpdateMessageRequestBody.builder()
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                .build()
            )
            resp = self._client().im.v1.message.update(req)
            if not resp.success:
                print(f"飞书状态更新失败: code={resp.code}, msg={resp.msg}")
        except Exception as exc:
            print(f"飞书状态更新异常: {exc}")
