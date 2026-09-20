@echo off
chcp 65001 > nul
cd /d %~dp0
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name "PUMA STOCK PRO" --collect-all PySide6 --collect-all websockets app.py
if exist "dist\PUMA STOCK PRO\PUMA STOCK PRO.exe" (
  echo.
  echo EXE 생성 완료: dist\PUMA STOCK PRO\PUMA STOCK PRO.exe
) else (
  echo EXE 생성에 실패했습니다. 위 오류를 확인하세요.
)
pause
