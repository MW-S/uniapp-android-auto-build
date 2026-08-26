import os
import subprocess
import time

from pipeline.common import StepResult

BUILD_TIMEOUT_SECONDS = 1800
TAIL_LINES = 40


def run(cfg: dict) -> StepResult:
    try:
        android_cfg = cfg["android"]
        project_dir = android_cfg["project_dir"]
        apk_output = android_cfg["apk_output"]

        if not os.path.isdir(project_dir):
            return StepResult.fail_result(f"Android壳工程目录不存在: {project_dir}")

        gradlew_path = os.path.join(project_dir, "gradlew.bat")
        if not os.path.isfile(gradlew_path):
            return StepResult.fail_result(f"Android壳工程目录下未找到gradlew.bat: {gradlew_path}")

        apk_dir = os.path.normpath(os.path.join(project_dir, apk_output))
        fallback_dir = os.path.normpath(
            os.path.join(project_dir, "App", "build", "outputs", "apk", "release")
        )
        _existing, _existing_dir = _scan_apks(apk_dir, fallback_dir)
        if _existing:
            command = "gradlew.bat assembleRelease"
            mode_note = ""
        else:
            command = "gradlew.bat clean assembleRelease"
            mode_note = "APK产物缺失，执行clean全量重建（gradle的UP-TO-DATE缓存不会补生成被删除的APK）"

        build_start = time.time()
        try:
            proc = subprocess.run(
                command,
                cwd=project_dir,
                shell=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=BUILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return StepResult.fail_result(
                f"Android构建超时（超过{BUILD_TIMEOUT_SECONDS}秒）: {command}"
            )

        if proc.returncode != 0:
            output_lines = ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines()
            tail = "\n".join(output_lines[-TAIL_LINES:])
            return StepResult.fail_result(
                f"{command}构建失败，退出码 {proc.returncode}，输出最后{TAIL_LINES}行:\n{tail}",
                returncode=proc.returncode,
            )

        if not os.path.isdir(apk_dir):
            return StepResult.fail_result(f"未找到本次构建产物，apk输出目录不存在: {apk_dir}")

        candidates, found_dir = _scan_apks(apk_dir, fallback_dir)
        if not candidates:
            return StepResult.fail_result(
                f"未找到本次构建产物，以下目录均没有*.apk:\n{apk_dir}\n{fallback_dir}"
            )

        apk_mtime, apk_path = candidates[0]

        apk_name = os.path.basename(apk_path)
        apk_size = os.path.getsize(apk_path)
        extra_note = ""
        if found_dir != apk_dir:
            extra_note = f"（产物位于gradle默认输出目录: {found_dir}）"
        if mode_note:
            extra_note = f"（{mode_note}）{extra_note}"
        elif not extra_note and apk_mtime < build_start:
            extra_note = "（增量构建UP-TO-DATE，资源无变化，沿用现有APK）"
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
