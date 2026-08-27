import os

import yaml


class ConfigError(Exception):
    pass


FEISHU_REQUIRED_FIELDS = ("app_id", "app_secret", "trigger_keywords")

PROJECT_REQUIRED_FIELDS = (
    "key",
    "name",
    "git.repo_dir",
    "git.branch",
    "hbuilderx.cli_path",
    "hbuilderx.project_name",
    "hbuilderx.appid",
    "android.project_dir",
    "android.assets_dir",
    "android.apk_output",
    "kodcloud.webdav_url",
    "kodcloud.username",
    "kodcloud.password",
    "kodcloud.remote_dir",
)


def _get_nested(mapping: dict, field_name: str):
    section, key = field_name.split(".", 1)
    value = mapping.get(section)
    if not isinstance(value, dict):
        return None
    return value.get(key)


def _validate_project(project, index: int) -> None:
    label = f"projects[{index}]"
    if not isinstance(project, dict):
        raise ConfigError(f"{label} 必须是字典结构")
    key = project.get("key")
    if isinstance(key, str) and key.strip():
        label = f"projects[{index}]({key.strip()})"
    for field_name in PROJECT_REQUIRED_FIELDS:
        value = _get_nested(project, field_name) if "." in field_name else project.get(field_name)
        if value is None:
            raise ConfigError(f"配置缺少必填字段: {label}.{field_name}")
        if isinstance(value, str) and not value.strip():
            raise ConfigError(f"配置字段 {label}.{field_name} 不能为空")
    aliases = project.get("aliases")
    if aliases is not None and (not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases)):
        raise ConfigError(f"配置字段 {label}.aliases 必须是字符串列表")


def validate_config(cfg: dict) -> None:
    feishu = cfg.get("feishu")
    if not isinstance(feishu, dict):
        raise ConfigError("配置缺少必填节点: feishu")
    for field_name in FEISHU_REQUIRED_FIELDS:
        value = feishu.get(field_name)
        if field_name == "trigger_keywords":
            if not isinstance(value, list) or not value:
                raise ConfigError("配置字段 feishu.trigger_keywords 必须是非空列表")
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ConfigError(f"配置缺少有效的必填字段: feishu.{field_name}")
    projects = cfg.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ConfigError("配置缺少必填节点: projects（至少包含一个项目）")
    keys = []
    for index, project in enumerate(projects):
        _validate_project(project, index)
        keys.append(str(project["key"]).strip())
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ConfigError(f"projects 中存在重复的 key: {', '.join(duplicates)}")
    default_project = cfg.get("default_project")
    if default_project is not None:
        if not isinstance(default_project, str) or default_project.strip() not in keys:
            raise ConfigError(f"default_project 必须指向已有项目的 key，可选值: {', '.join(keys)}")


def load_config(path: str = "config.yaml") -> dict:
    if not os.path.isfile(path):
        raise ConfigError(
            f"未找到配置文件: {os.path.abspath(path)}，"
            "请复制 config.yaml.example 为 config.yaml 并填写"
        )
    with open(path, "r", encoding="utf-8") as fp:
        try:
            cfg = yaml.safe_load(fp)
        except yaml.YAMLError as exc:
            msg = f"配置文件解析失败: {exc}"
            if "unknown escape character" in str(exc):
                msg += (
                    "\n提示: YAML双引号中反斜杠是转义符，Windows路径请改用单引号包裹，"
                    "例如 project_dir: 'I:\\Work\\我的项目'"
                )
            raise ConfigError(msg)
    if not isinstance(cfg, dict):
        raise ConfigError("配置文件内容无效，根节点必须是字典")
    validate_config(cfg)
    return cfg


def project_terms(project: dict) -> list[str]:
    terms = [str(project.get("key", "")), str(project.get("name", ""))]
    terms.extend(str(a) for a in (project.get("aliases") or []))
    return [t for t in terms if t and t.strip()]


def find_project(cfg: dict, text: str):
    if not text:
        return None
    lowered = text.lower()
    candidates = []
    for project in cfg.get("projects", []):
        matched = [t for t in project_terms(project) if t.lower() in lowered]
        if matched:
            candidates.append((max(len(t) for t in matched), project))
    if not candidates:
        return None
    best = max(length for length, _ in candidates)
    winners = [p for length, p in candidates if length == best]
    if len(winners) > 1:
        return None
    return winners[0]


def select_project(cfg: dict, identifier: str):
    ident = (identifier or "").strip()
    if not ident:
        return None
    lowered = ident.lower()
    for project in cfg.get("projects", []):
        if str(project.get("key", "")).strip().lower() == lowered:
            return project
        if str(project.get("name", "")).strip().lower() == lowered:
            return project
    return find_project(cfg, ident)


def default_project(cfg: dict):
    projects = cfg.get("projects", [])
    if len(projects) == 1:
        return projects[0]
    default_key = cfg.get("default_project")
    if default_key:
        return next((p for p in projects if str(p.get("key", "")).strip() == default_key.strip()), None)
    return None


def projects_summary(cfg: dict) -> str:
    default_key = (cfg.get("default_project") or "").strip()
    lines = []
    for project in cfg.get("projects", []):
        key = str(project.get("key", "")).strip()
        name = str(project.get("name", "")).strip()
        aliases = "、".join(str(a) for a in (project.get("aliases") or [])) or "无"
        mark = "，默认" if key == default_key else ""
        lines.append(f"- {name}（key={key}{mark}，触发词: {aliases}）")
    return "\n".join(lines)


def repo_resources_dir(project: dict) -> str:
    return os.path.abspath(
        os.path.join(
            project["git"]["repo_dir"],
            "unpackage",
            "resources",
            project["hbuilderx"]["appid"],
        )
    )
