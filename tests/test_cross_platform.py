import importlib
import os
import subprocess
import sys
from unittest.mock import patch

import pytest


def test_hbuilderx_linux_platform_rejected(tmp_path):
    cli_path = tmp_path / "cli.exe"
    cli_path.write_text("fake cli")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    cfg = {
        "hbuilderx": {
            "cli_path": str(cli_path),
            "project_name": "testproj",
            "appid": "__UNI__TEST",
        },
        "git": {
            "repo_dir": str(repo_dir),
            "branch": "master",
        },
        "android": {
            "project_dir": str(tmp_path / "android"),
            "assets_dir": str(tmp_path / "assets"),
            "apk_output": "App/build/outputs/apk/release",
        },
    }
    original_platform = sys.platform
    with patch("sys.platform", "linux"):
        with patch("pipeline.hbuilderx_step.subprocess.run", side_effect=[]):
            from pipeline.hbuilderx_step import run
            res = run(cfg)
    assert not res.ok
    assert "不支持 HBuilderX 本地打包" in str(res.log)


def test_hbuilderx_cli_encoding_darwin():
    original_platform = sys.platform
    import pipeline.hbuilderx_step as m
    with patch("sys.platform", "darwin"):
        importlib.reload(m)
        assert m.CLI_ENCODING == "utf-8"
    with patch("sys.platform", original_platform):
        importlib.reload(m)


def test_hbuilderx_cli_encoding_win():
    original_platform = sys.platform
    import pipeline.hbuilderx_step as m
    with patch("sys.platform", "win32"):
        importlib.reload(m)
        assert m.CLI_ENCODING == "gbk"
    with patch("sys.platform", original_platform):
        importlib.reload(m)


def test_android_gradle_win_uses_bat(tmp_path):
    project_dir = tmp_path / "android_project"
    project_dir.mkdir()
    cfg = {
        "android": {
            "project_dir": str(project_dir),
            "apk_output": "App/build/outputs/apk/release",
            "assets_dir": str(tmp_path / "assets"),
        },
        "hbuilderx": {"appid": "__UNI__TEST"},
        "git": {"repo_dir": str(tmp_path / "repo")},
    }

    def fake_isdir(path):
        if path == str(project_dir):
            return True
        return False

    def fake_isfile(path):
        if path.endswith("gradlew.bat"):
            return True
        return False

    fake_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("sys.platform", "win32"):
        with patch("pipeline.android_build_step.os.path.isdir", side_effect=fake_isdir):
            with patch("pipeline.android_build_step.os.path.isfile", side_effect=fake_isfile):
                with patch("pipeline.android_build_step.subprocess.run", return_value=fake_proc) as mock_run:
                    from pipeline.android_build_step import run
                    try:
                        run(cfg)
                    except Exception:
                        pass
    assert mock_run.called
    call_args = mock_run.call_args
    args = call_args[0][0]
    kwargs = call_args[1]
    assert args[0].endswith("gradlew.bat")
    assert kwargs.get("shell", False) is False


def test_android_gradle_darwin_uses_script(tmp_path):
    project_dir = tmp_path / "android_project"
    project_dir.mkdir()
    cfg = {
        "android": {
            "project_dir": str(project_dir),
            "apk_output": "App/build/outputs/apk/release",
            "assets_dir": str(tmp_path / "assets"),
        },
        "hbuilderx": {"appid": "__UNI__TEST"},
        "git": {"repo_dir": str(tmp_path / "repo")},
    }

    def fake_isdir(path):
        if path == str(project_dir):
            return True
        return False

    def fake_isfile(path):
        if path.endswith(os.sep + "gradlew") or path.endswith("/gradlew"):
            return True
        return False

    fake_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("sys.platform", "darwin"):
        with patch("pipeline.android_build_step.os.path.isdir", side_effect=fake_isdir):
            with patch("pipeline.android_build_step.os.path.isfile", side_effect=fake_isfile):
                with patch("pipeline.android_build_step.os.chmod") as mock_chmod:
                    with patch("pipeline.android_build_step.subprocess.run", return_value=fake_proc) as mock_run:
                        from pipeline.android_build_step import run
                        try:
                            run(cfg)
                        except Exception:
                            pass
    assert mock_run.called
    call_args = mock_run.call_args
    args = call_args[0][0]
    assert not args[0].endswith(".bat")
    assert mock_chmod.called


def test_android_gradle_unix_uses_sh(tmp_path):
    project_dir = tmp_path / "android_project"
    project_dir.mkdir()
    cfg = {
        "android": {
            "project_dir": str(project_dir),
            "apk_output": "App/build/outputs/apk/release",
            "assets_dir": str(tmp_path / "assets"),
        },
        "hbuilderx": {"appid": "__UNI__TEST"},
        "git": {"repo_dir": str(tmp_path / "repo")},
    }

    def fake_isdir(path):
        if path == str(project_dir):
            return True
        return False

    def fake_isfile(path):
        if path.endswith(os.sep + "gradlew") or path.endswith("/gradlew"):
            return True
        return False

    fake_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("sys.platform", "linux"):
        with patch("pipeline.android_build_step.os.path.isdir", side_effect=fake_isdir):
            with patch("pipeline.android_build_step.os.path.isfile", side_effect=fake_isfile):
                with patch("pipeline.android_build_step.os.chmod") as mock_chmod:
                    with patch("pipeline.android_build_step.subprocess.run", return_value=fake_proc) as mock_run:
                        from pipeline.android_build_step import run
                        try:
                            run(cfg)
                        except Exception:
                            pass
    assert mock_run.called
    call_args = mock_run.call_args
    args = call_args[0][0]
    assert not args[0].endswith(".bat")
    assert mock_chmod.called
