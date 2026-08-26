import os
import re
import time
from datetime import datetime

import requests
from webdav3.client import Client
from webdav3.exceptions import ConnectionException
from webdav3.exceptions import NoConnection

try:
    from webdav3.exceptions import ResponseError
except ImportError:
    from webdav3.exceptions import ResponseErrorCode as ResponseError

from pipeline.common import StepResult

CONNECTION_ERRORS = (
    NoConnection,
    ConnectionException,
    requests.exceptions.ConnectionError,
    requests.exceptions.SSLError,
    requests.exceptions.Timeout,
)


def run(cfg: dict, apk_path: str) -> StepResult:
    try:
        if not apk_path or not os.path.isfile(apk_path):
            return StepResult.fail_result(f"apk文件不存在: {apk_path}")

        kod_cfg = cfg["kodcloud"]
        webdav_url = kod_cfg["webdav_url"]
        username = kod_cfg["username"]
        password = kod_cfg["password"]
        remote_dir = kod_cfg["remote_dir"]

        options = {
            "webdav_hostname": webdav_url,
            "webdav_login": username,
            "webdav_password": password,
        }
        client = Client(options)

        dir_prefix = remote_dir if remote_dir.endswith("/") else remote_dir + "/"
        if not client.check(dir_prefix):
            client.mkdir(dir_prefix, recursive=True)
            deadline = time.time() + 30
            while not client.check(dir_prefix):
                if time.time() >= deadline:
                    return StepResult.fail_result(f"创建远端目录后仍无法访问: {dir_prefix}")
                time.sleep(2)

        prefix = (kod_cfg.get("apk_prefix") or cfg.get("key") or "app").strip()
        prefix = re.sub(r'[\\/:*?"<>|]', "_", prefix)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        apk_name = f"{prefix}_{stamp}.apk"
        remote_path = dir_prefix + apk_name
        client.upload_sync(remote_path=remote_path, local_path=apk_path)

        if not client.check(remote_path):
            return StepResult.fail_result(f"上传后校验失败，远端不存在文件: {remote_path}")

        apk_size = os.path.getsize(apk_path)
        return StepResult.ok_result(
            f"上传成功，远端路径: {remote_path}，文件大小: {apk_size} 字节",
            remote_path=remote_path,
            apk_size=apk_size,
            apk_name=apk_name,
        )
    except ResponseError as exc:
        code = getattr(exc, "code", None)
        if code in (401, 403) or "401" in str(exc) or "403" in str(exc):
            return StepResult.fail_result("WebDAV鉴权失败，请检查账号密码")
        return StepResult.fail_result(f"WebDAV响应错误: {exc}")
    except CONNECTION_ERRORS as exc:
        return StepResult.fail_result(f"无法连接WebDAV服务: {exc}")
    except Exception as exc:
        return StepResult.fail_result(f"可道云上传步骤异常: {exc}")
