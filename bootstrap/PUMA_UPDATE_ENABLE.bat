@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PUMA STOCK PRO 업데이트 기능 활성화

if not exist "runtime\python.exe" (
  echo.
  echo [오류] 이 파일을 PUMA 프로그램 최상위 폴더에 넣은 뒤 실행하세요.
  echo runtime\python.exe 를 찾을 수 없습니다.
  echo.
  pause
  exit /b 1
)

"runtime\python.exe" "PUMA_UPDATE_ENABLE.py"
if errorlevel 1 pause
