@echo off
setlocal
cd /d "%~dp0"
uv run python tools/sim_train_tui.py
endlocal
