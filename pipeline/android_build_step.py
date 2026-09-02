import os
import subprocess
import sys
import time

from pipeline.common import StepResult

BUILD_TIMEOUT_SECONDS = 1800
TAIL_LINES = 40


def _run_ensure_android_env(project_dir: str) -> str | None:
    """Invoke the Docker helper script (idempotent) if present.

    The script lives at ``<repo>/docker/ensure-android-env.sh`` in source mode,
    which Docker copies to ``/app/docker/ensure-android-env.sh`` inside the
    container. It:

    * parses the shell project's App/build.gradle,
    * validates JDK compatibility against the detected AGP version,
    * and installs any missing ``compileSdk``/``buildToolsVersion``/``ndkVersion``
      via ``sdkmanager``.

    Returns ``None`` on success, or a non-empty warning string on failure.
    Failure is *non-fatal*: we still proceed to ``./gradlew clean assembleRelease``
    because Gradle often has better built-in error messages for SDK mismatches.
    """
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "docker", "ensure-android-env.sh")
    )
    if not os.path.isfile(script_path):
        return None
    if os.name == "nt":
        # The script is pure bash and is only meant to run inside the Docker
        # image; silently skip on Windows.
        return None
    env = os.environ.copy()
    env.setdefault("ANDROID_SDK_ROOT", "/opt/android-sdk")
    if not env.get("JAVA_HOME"):
        common_candidates = [
            "/usr/lib/jvm/java-17-openjdk-amd64",
            "/usr/lib/jvm/java-17-openjdk-arm64",
            "/usr/lib/jvm/java-17-openjdk",
        ]
        for cand in common_candidates:
            if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, "bin", "java")):
                env["JAVA_HOME"] = cand
                break
    try:
        proc = subprocess.run(
            ["bash", script_path, project_dir],
            cwd=project_dir,
            env=env,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=600,
        )
    except FileNotFoundError:
        return "（未找到 bash，跳过 Android SDK 现场对齐，若缺少 SDK 请先安装）"
    except subprocess.TimeoutExpired:
        return "（Android SDK 对齐超时超过 600 秒，可能是 sdkmanager 下载较慢，建议手动安装或检查网络）"
    if proc.returncode != 0:
        tail = "\n".join(((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines()[-TAIL_LINES:])
        return f"（Android SDK 现场对齐未成功，exit={proc.returncode}，末段输出：{tail}）"
    return None


def _normalize_gradle_project_env(base_env: dict, project_dir: str) -> dict:
    """Ensure Gradle sees a usable JAVA_HOME and local SDK path.

    On Linux hosts / Docker we intentionally avoid ``local.properties``: the
    compiled-in environment variables ANDROID_SDK_ROOT / JAVA_HOME are the
    source of truth. If the project already ships ``local.properties`` we
    honour it, but when it is missing we do **not** create a fallback file
    with host-specific paths.
    """
    env = dict(base_env)
    local_prop = os.path.join(project_dir, "local.properties")
    if os.path.isfile(local_prop):
        return env
    env.setdefault("ANDROID_SDK_ROOT", "/opt/android-sdk")
    env.setdefault("ANDROID_HOME", env["ANDROID_SDK_ROOT"])
    if not env.get("JAVA_HOME") and sys.platform.startswith("linux"):
        for cand in (
            "/usr/lib/jvm/java-17-openjdk-amd64",
            "/usr/lib/jvm/java-17-openjdk-arm64",
            "/usr/lib/jvm/java-17-openjdk",
        ):
            if os.path.isfile(os.path.join(cand, "bin", "java")):
                env["JAVA_HOME"] = cand
                break
    return env


def run(cfg: dict) -> StepResult:
    try:
        android_cfg = cfg["android"]
        project_dir = android_cfg["project_dir"]
        apk_output = android_cfg.get("apk_output") or ""

        if not os.path.isdir(project_dir):
            return StepResult.fail_result(f"Android壳工程目录不存在: {project_dir}")

        notes = []
        env_align_warn = _run_ensure_android_env(project_dir)
        if env_align_warn:
            notes.append(env_align_warn)

        if sys.platform.startswith("win"):
            gradlew_script = "gradlew.bat"
        else:
            gradlew_script = "gradlew"
        gradlew_path = os.path.join(project_dir, gradlew_script)
        if not os.path.isfile(gradlew_path):
            return StepResult.fail_result(f"未找到gradle wrapper脚本: {gradlew_path}")

        if not sys.platform.startswith("win"):
            os.chmod(gradlew_path, 0o755)

        apk_dir = os.path.normpath(os.path.join(project_dir, apk_output)) if apk_output else ""
        fallback_dir = os.path.normpath(
            os.path.join(project_dir, "App", "build", "outputs", "apk", "release")
        )
        # Option 1 (user choice): always clean before assembleRelease so we get a freshly
        # compiled & freshly signed APK every time. This avoids the confusing behaviour
        # where Gradle happily reports UP-TO-DATE for an unchanged www tree and keeps the
        # same APK file on disk (even when the user re-runs the pipeline expecting a new
        # artifact). If anything non-deterministic changes inside the Android shell project
        # (build config, native libs, signing certificate, manifest tweaks, ...) this also
        # guarantees the rebuild picks it up.
        command = [gradlew_path, "clean", "assembleRelease"]
        mode_note = "每次构建前执行 clean 全量重建（保证产出重新编译/重新签名的 APK）"

        build_env = _normalize_gradle_project_env(os.environ, project_dir)
        build_start = time.time()
        try:
            proc = subprocess.run(
                command,
                cwd=project_dir,
                env=build_env,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=BUILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return StepResult.fail_result(
                f"Android构建超时（超过{BUILD_TIMEOUT_SECONDS}秒）: {' '.join(command)}"
            )

        if proc.returncode != 0:
            output_lines = ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines()
            tail = "\n".join(output_lines[-TAIL_LINES:])
            note = "；".join(notes) if notes else ""
            return StepResult.fail_result(
                f"{' '.join(command)}构建失败，退出码 {proc.returncode}，输出最后{TAIL_LINES}行:\n{tail}"
                + (note and f"\n前置说明: {note}" or ""),
                returncode=proc.returncode,
            )

        if apk_dir and not os.path.isdir(apk_dir):
            return StepResult.fail_result(f"未找到本次构建产物，apk输出目录不存在: {apk_dir}")

        candidates, found_dir = _scan_apks(apk_dir if apk_dir else fallback_dir, fallback_dir)
        if not candidates:
            return StepResult.fail_result(
                f"未找到本次构建产物，以下目录均没有*.apk:\n{apk_dir or '（未配置，仅使用默认目录）'}\n{fallback_dir}"
            )

        apk_mtime, apk_path = candidates[0]

        apk_name = os.path.basename(apk_path)
        apk_size = os.path.getsize(apk_path)
        extra_note = ""
        if found_dir != apk_dir:
            extra_note = f"（产物位于gradle默认输出目录: {found_dir}）"
        if notes:
            extra_note = "；".join(notes) + " | " + extra_note
        if mode_note:
            extra_note = f"（{mode_note}）{extra_note}"
        return StepResult.ok_result(
            f"Android构建成功，产物: {apk_name}（{apk_size} 字节），路径: {apk_path}{extra_note}",
            apk_path=apk_path,
            apk_size=apk_size,
            apk_name=apk_name,
        )
    except Exception as exc:
        return StepResult.fail_result(f"Android构建步骤异常: {exc}")


def _scan_apks(apk_dir: str, fallback_dir: str):
    candidates = _find_apks(apk_dir)
    if candidates:
        return candidates, apk_dir
    candidates = _find_apks(fallback_dir)
    if candidates:
        return candidates, fallback_dir
    return [], None


def _find_apks(apk_dir: str):
    candidates = []
    if not os.path.isdir(apk_dir):
        return candidates
    for root, _dirs, files in os.walk(apk_dir):
        for file_name in files:
            if file_name.lower().endswith(".apk"):
                file_path = os.path.join(root, file_name)
                candidates.append((os.path.getmtime(file_path), file_path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates
