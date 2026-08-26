import copy

import pytest

from pipeline.config import ConfigError
from pipeline.config import validate_config

MINIMAL_PROJECT = {
    "key": "demo-app",
    "name": "示例项目",
    "aliases": ["demo"],
    "git": {
        "repo_dir": "D:/projects/uniapp-demo",
        "branch": "main",
    },
    "hbuilderx": {
        "cli_path": "C:/Program Files/HBuilderX/cli.exe",
        "project_name": "uniapp-demo",
        "appid": "__UNI__TEST001",
    },
    "android": {
        "project_dir": "D:/projects/uniapp-android",
        "assets_dir": "app/src/main/assets/apps/__UNI__TEST001",
        "apk_output": "app/build/outputs/apk/release",
    },
    "kodcloud": {
        "webdav_url": "https://example.com/?webdav/",
        "username": "user",
        "password": "pass",
        "remote_dir": "/builds/demo-app/",
    },
}


def minimal_cfg():
    return {
        "feishu": {
            "app_id": "cli_test",
            "app_secret": "secret",
            "trigger_keywords": ["打包", "构建"],
        },
        "projects": [copy.deepcopy(MINIMAL_PROJECT)],
    }


def test_validate_config_accepts_minimal_valid_cfg():
    validate_config(minimal_cfg())


def test_validate_config_missing_projects_raises():
    cfg = minimal_cfg()
    del cfg["projects"]
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_validate_config_missing_required_field_raises():
    cfg = minimal_cfg()
    del cfg["projects"][0]["git"]["branch"]
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_validate_config_duplicate_project_key_raises():
    cfg = minimal_cfg()
    second = copy.deepcopy(MINIMAL_PROJECT)
    second["key"] = "demo-app"
    cfg["projects"].append(second)
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_validate_config_default_project_unknown_key_raises():
    cfg = minimal_cfg()
    cfg["default_project"] = "no-such-key"
    with pytest.raises(ConfigError):
        validate_config(cfg)