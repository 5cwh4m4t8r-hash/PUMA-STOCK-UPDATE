@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PUMA STOCK PRO v2.9.4 CLEAN SETUP

echo ==========================================
echo   PUMA STOCK PRO v2.9.4 CLEAN 설치
echo ==========================================
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo [오류] Python이 설치되어 있지 않거나 py 명령을 찾을 수 없습니다.
  echo Python 3.11 또는 3.12 설치 후 다시 실행하세요.
  echo 설치할 때 "Add python.exe to PATH"를 체크하세요.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 전용 가상환경을 생성합니다...
  py -3 -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [1/3] 기존 가상환경을 사용합니다.
)

echo [2/3] pip를 업데이트합니다...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo [3/3] PUMA 필수 모듈을 설치합니다...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo ==========================================
echo   설치 완료
echo   이제 START_PUMA.bat 를 더블클릭하세요.
echo ==========================================
echo.
pause
exit /b 0

:fail
echo.
echo [실패] 설치 중 오류가 발생했습니다.
echo 위 오류 내용을 확인하세요.
pause
exit /b 1
