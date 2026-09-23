@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py -3 app.py
)

if errorlevel 1 (
  echo.
  echo PUMA 실행 중 오류가 발생했습니다.
  echo Python/PySide6가 설치되어 있는지 확인하세요.
  pause
)
