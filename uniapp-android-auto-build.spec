# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for uniapp-android-auto-build.

Produces a single-file console executable that bundles:
- The full Python pipeline code (bot, pipeline, web console)
- Required data files:
    - Web templates & static assets (Flask)
    - scripts/normalize-app-manifest.js     (pipeline fallback normalizer, invoked when the
                                              uni-app repo has not embedded its own copy)
    - scripts/REPO__normalize-app-manifest.self-contained.js
                                              (template that users copy into each uni-app repo
                                               to get the "self-contained, relative-path" pattern)
    - scripts/how_to_make_repo_self_contained.md
                                              (companion guide for the self-contained pattern)
    - config.yaml.example                     (first-run config template)
- Hidden imports that PyInstaller cannot detect automatically because they are used
  through dynamic imports or by nested packages (lark ws client, Flask glue, webdavclient3).

Run via: build_exe.bat  (Windows)  or  ./build_exe.sh  (macOS/Linux)
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ---------------------------------------------------------------- data files
datas = [
    # Flask web console assets
    ("web/templates", "web/templates"),
    ("web/static",    "web/static"),

    # Fallback + templates bundled inside the exe so it is fully self-contained.
    # Pipeline code resolves them against <pipeline_root>/scripts using __file__.
    ("scripts/normalize-app-manifest.js",                                      "scripts"),
    ("scripts/REPO__normalize-app-manifest.self-contained.js",                 "scripts"),
    ("scripts/how_to_make_repo_self_contained.md",                             "scripts"),

    # First-run config template. Also copied next to the exe by build_exe.* for easy access.
    ("config.yaml.example",                                                    "."),
]

binaries = []
hiddenimports = []

# ---------------------------------------------------------------- collect_all
# lark_oapi has deep subpackages (ws client, event handlers, openapi endpoints)
for pkg in ("lark_oapi", "flask", "webdavclient3", "requests", "yaml", "urllib3"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception:
        # If a package isn't importable at build time (e.g. user skips installing it),
        # we still want the spec to be buildable; missing modules will surface at runtime.
        pkg_datas, pkg_binaries, pkg_hidden = [], [], collect_submodules(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += list(pkg_hidden)

# Extra hidden imports that collect_all sometimes misses for our specific code paths:
hiddenimports += [
    # Flask / Werkzeug / Jinja2 subpackages used at runtime by the web console
    "flask.app",
    "flask.json.provider",
    "werkzeug.serving",
    "werkzeug.routing",
    "jinja2.ext",

    # Feishu websocket client (lark-oapi). Note: the SDK exposes two import forms:
    #   1) "import lark_oapi.ws"   (official, used by bot code)
    #   2) "import lark.ws"        (alias used in older docs; usually resolves to the same module
    #                                but PyInstaller cannot statically see it, so we list both and
    #                                ignore a "not found" warning if the alias is not installed)
    "lark_oapi.ws",
    "lark_oapi.api.contact.v3",
    "lark_oapi.api.im.v1",
    "lark_oapi.event.callback",

    # HTTP / TLS stack used by both Feishu client and KodCloud (webdavclient3 + requests)
    "requests",
    "requests.adapters",
    "urllib3.util.ssl_",
    "certifi",
    "charset_normalizer",

    # YAML config parser
    "yaml",
    "_yaml",

    # Pipeline subpackages (all imported transitively, but belt-and-braces for one-file build)
    "bot.feishu_bot",
    "pipeline.config",
    "pipeline.runner",
    "pipeline.build_manager",
    "pipeline.git_step",
    "pipeline.hbuilderx_step",
    "pipeline.copy_resources_step",
    "pipeline.android_build_step",
    "pipeline.kodcloud_upload_step",
    "pipeline.common",
]
hiddenimports = list(dict.fromkeys(hiddenimports))  # dedupe while keeping order


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "PyQt5", "PySide2", "tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="uniapp-android-auto-build",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
