@echo off
setlocal
cd /d %~dp0

REM ============================================================
REM Step 1/5: Ensure dev dependencies (PyInstaller + runtime deps)
REM ============================================================
echo [1/5] Checking Python / dev dependencies...

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] python.exe not found in PATH. Install Python 3.10+ and re-open the terminal.
    goto :failed
)

REM Try to import PyInstaller AND our core runtime dependencies.
REM If anything is missing, install via requirements-dev.txt which transitively includes requirements.txt.
python -c "import PyInstaller, yaml, flask, lark_oapi, requests, webdavclient3" >nul 2>nul
if errorlevel 1 (
    echo   Missing one or more dependencies -- running: python -m pip install -r requirements-dev.txt ...
    call python -m pip install --upgrade pip || goto :failed
    call python -m pip install -r requirements-dev.txt || goto :failed
) else (
    echo   pyinstaller + runtime deps ready.
)

REM Also guarantee scripts/ directory used by fallback normalizer exists at build time:
if not exist "scripts\normalize-app-manifest.js" (
    echo [ERROR] scripts\normalize-app-manifest.js missing from project root. Did you delete it?
    goto :failed
)
if not exist "scripts\REPO__normalize-app-manifest.self-contained.js" (
    echo [ERROR] scripts\REPO__normalize-app-manifest.self-contained.js missing from project root.
    goto :failed
)

REM ============================================================
REM Step 2/5: Clean previous build artifacts for reproducible output
REM ============================================================
echo.
echo [2/5] Cleaning old build dirs...
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"
mkdir "dist" 2>nul

REM ============================================================
REM Step 3/5: Build single-file executable via PyInstaller spec
REM ============================================================
echo.
echo [3/5] Running PyInstaller (this can take 1-3 min, please wait)...
call python -m PyInstaller uniapp-android-auto-build.spec --noconfirm --clean || goto :failed

if not exist "dist\uniapp-android-auto-build.exe" (
    echo [ERROR] PyInstaller succeeded but dist\uniapp-android-auto-build.exe was not produced.
    goto :failed
)

REM ============================================================
REM Step 4/5: Copy companion assets next to the exe for easy distribution
REM ============================================================
echo.
echo [4/5] Copying distribution assets into dist\ ...

copy /y "config.yaml.example"                                              "dist\config.yaml.example" >nul || goto :failed
if not exist "dist\scripts" mkdir "dist\scripts" >nul
copy /y "scripts\REPO__normalize-app-manifest.self-contained.js"               "dist\scripts\REPO__normalize-app-manifest.self-contained.js" >nul || goto :failed
copy /y "scripts\how_to_make_repo_self_contained.md"                          "dist\scripts\how_to_make_repo_self_contained.md"          >nul || goto :failed
REM The FALLBACK normalizer is already bundled INSIDE the exe via PyInstaller datas.
REM We still place a copy next to the exe so users can inspect / diff it if needed:
copy /y "scripts\normalize-app-manifest.js"                                   "dist\scripts\normalize-app-manifest.js"                   >nul || goto :failed
REM Start scripts for source mode are also handy when distributing to Windows users:
if exist "start.bat" copy /y "start.bat" "dist\start.bat" >nul
REM Docs:
if exist "README.md"        copy /y "README.md"        "dist\README.md"        >nul
if exist "README.zh-CN.md"  copy /y "README.zh-CN.md"  "dist\README.zh-CN.md"  >nul

REM ============================================================
REM Step 5/5: Validate final dist layout + smoke-run the exe
REM ============================================================
echo.
echo [5/5] Validating dist\ layout + quick smoke test...

set "EXE=dist\uniapp-android-auto-build.exe"
for %%F in (
    "%EXE%"
    "dist\config.yaml.example"
    "dist\scripts\REPO__normalize-app-manifest.self-contained.js"
    "dist\scripts\normalize-app-manifest.js"
    "dist\scripts\how_to_make_repo_self_contained.md"
) do if not exist %%~F (
    echo [ERROR] Expected file missing: %%~F
    goto :failed
)

REM The exe supports --list to print platform info + project list.
REM Run it with --config pointing to a non-existent file just to get the platform banner (it will exit after printing).
"%EXE%" --list --config "dist\_smoke_missing_config.yaml" >nul 2>&1
if errorlevel 1 (
    REM --list without config still prints platform diagnostic before the missing-config error, so exit code>0 is expected.
    REM We only care that the exe actually started without "DLL load failed / ModuleNotFound".
    echo   exe started OK (non-zero exit from missing config is expected here).
) else (
    echo   exe started OK.
)

echo.
echo ========================================
echo  Build succeeded (Windows x64 single-file exe)
echo ========================================
echo  Executable:
echo    dist\uniapp-android-auto-build.exe
echo  Config template:
echo    dist\config.yaml.example          (copy as dist\config.yaml and edit it)
echo  Companion files for self-contained uni-app repo onboarding:
echo    dist\scripts\REPO__normalize-app-manifest.self-contained.js
echo    dist\scripts\normalize-app-manifest.js           ^(same file bundled inside exe as fallback^)
echo    dist\scripts\how_to_make_repo_self_contained.md
echo  Quick start on target machine:
echo    1. Copy all files from dist\ to the same folder.
echo    2. Run uniapp-android-auto-build.exe once to generate config.yaml from template.
echo    3. Edit config.yaml, re-launch exe.
echo ========================================
endlocal
exit /b 0

:failed
echo.
echo ========================================
echo  Build FAILED - inspect the output above.
echo ========================================
endlocal
exit /b 1

