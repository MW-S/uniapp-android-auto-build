@echo off
setlocal
cd /d %~dp0

python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [1/3] pyinstaller not found, installing...
    pip install pyinstaller || goto :failed
) else (
    echo [1/3] pyinstaller ready
)

echo [2/3] Building executable, please wait...
python -m PyInstaller uniapp-android-auto-build.spec --noconfirm --clean || goto :failed

echo [3/3] Copying config template...
copy /y config.yaml.example dist\config.yaml.example >nul

echo.
echo ========================================
echo Build succeeded!
echo   Executable:    dist\uniapp-android-auto-build.exe
echo   Config sample: dist\config.yaml.example
echo Distribute both files in the same folder.
echo Copy config.yaml.example to config.yaml and fill it in before first run.
echo ========================================
endlocal
exit /b 0

:failed
echo.
echo Build failed, see errors above
endlocal
exit /b 1
