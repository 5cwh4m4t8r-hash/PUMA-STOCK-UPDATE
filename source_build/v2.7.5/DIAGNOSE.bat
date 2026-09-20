@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== PUMA STOCK PRO 진단 =====
echo.
where py 2>nul
where python 2>nul
echo.
if exist ".venv\Scripts\python.exe" (
  echo [OK] PUMA 전용 Python 환경 존재
  ".venv\Scripts\python.exe" --version
  ".venv\Scripts\python.exe" -c "import PySide6,requests,websockets; print('[OK] 필수 패키지 정상')"
) else (
  echo [FAIL] .venv 환경 없음 - 1_SETUP.bat 실행 필요
)
echo.
if exist install_log.txt (
  echo install_log.txt가 있습니다. 오류가 났다면 이 파일을 보내주세요.
)
pause
