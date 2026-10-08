@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" doupi_gui.py
) else (
    python doupi_gui.py
)
if errorlevel 1 (
    echo 请安装 Python 3.10+，然后运行：python -m pip install ".[gui]"
    pause
)
