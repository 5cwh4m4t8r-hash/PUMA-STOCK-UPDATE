@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo PUMA 설치가 필요합니다. 먼저 1_SETUP.bat 를 실행하세요.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 (
  echo.
  echo 프로그램 실행 중 오류가 발생했습니다.
  pause
)
