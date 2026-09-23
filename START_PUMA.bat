@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "runtime\pythonw.exe" (
  start "" "%~dp0runtime\pythonw.exe" "%~dp0app.py"
  exit /b 0
)

if exist ".venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
  exit /b 0
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py -3 app.py
)

if errorlevel 1 (
  echo.
  echo PUMA 실행 중 오류가 발생했습니다.
  pause
)
