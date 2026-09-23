from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MANIFEST = "https://raw.githubusercontent.com/5cwh4m4t8r-hash/PUMA-STOCK-UPDATE/main/manifest.json"
TARGET_VERSION = "2.9.5"

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime" / "python.exe"
APP = ROOT / "app.py"
TRADER = ROOT / "puma_trader"

def fail(msg: str):
    print()
    print("[실패]", msg)
    print("이 창을 닫지 말고 내용을 확인하세요.")
    input("\nEnter를 누르면 종료합니다...")
    raise SystemExit(1)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()

def safe_extract(zpath: Path, dest: Path):
    base = dest.resolve()
    with zipfile.ZipFile(zpath, "r") as z:
        for info in z.infolist():
            name = str(info.filename or "").replace("\\", "/")
            p = Path(name)
            if not name or p.is_absolute() or ".." in p.parts:
                fail(f"안전하지 않은 업데이트 경로: {name}")
            out = (dest / p).resolve()
            if out != base and base not in out.parents:
                fail(f"업데이트 경로가 폴더를 벗어납니다: {name}")
        z.extractall(dest)

def source_root(dest: Path) -> Path:
    if (dest / "app.py").exists():
        return dest
    dirs = [p for p in dest.iterdir() if p.is_dir()]
    if len(dirs) == 1 and (dirs[0] / "app.py").exists():
        return dirs[0]
    fail("업데이트 패키지 구조를 확인할 수 없습니다.")

def main():
    print("==============================================")
    print(" PUMA STOCK PRO 업데이트 기능 활성화")
    print("==============================================")
    print()

    if not APP.exists() or not TRADER.exists():
        fail("이 파일은 PUMA 프로그램 최상위 폴더에서 실행해야 합니다.")
    if not RUNTIME.exists():
        fail("runtime\\python.exe가 없습니다. 포터블 완전체 폴더인지 확인하세요.")

    req = urllib.request.Request(MANIFEST, headers={"User-Agent":"PUMA-BOOTSTRAP/2.9.5"})
    with urllib.request.urlopen(req, timeout=20) as r:
        info = json.loads(r.read().decode("utf-8-sig"))

    version = str(info.get("version") or "").strip()
    url = str(info.get("url") or "").strip()
    expected = str(info.get("sha256") or "").strip().lower()
    if version != TARGET_VERSION:
        fail(f"부트스트랩 대상은 v{TARGET_VERSION}인데 서버 버전은 v{version}입니다.")
    if not url or not expected:
        fail("업데이트 서버 정보가 불완전합니다.")

    tmp = Path(tempfile.mkdtemp(prefix="puma_bootstrap_"))
    zpath = tmp / f"PUMA_STOCK_PRO_v{version}_UPDATE.zip"
    extract = tmp / "extract"
    extract.mkdir(parents=True, exist_ok=True)

    try:
        print(f"[1/4] v{version} 업데이트 다운로드...")
        req = urllib.request.Request(url, headers={"User-Agent":"PUMA-BOOTSTRAP/2.9.5"})
        with urllib.request.urlopen(req, timeout=60) as r, zpath.open("wb") as f:
            while True:
                chunk = r.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)

        print("[2/4] SHA256 검증...")
        actual = sha256(zpath)
        if actual != expected:
            fail("SHA256 검증 실패. 파일을 적용하지 않습니다.")

        print("[3/4] 업데이트 파일 적용...")
        safe_extract(zpath, extract)
        src = source_root(extract)

        backup = ROOT / "_bootstrap_backup_v2.9.4"
        backup.mkdir(exist_ok=True)
        for rel in [
            "app.py",
            "puma_trader/ui.py",
            "puma_trader/updater.py",
            "puma_trader/__init__.py",
            "PUMA_STOCK_PRO_ICON.svg",
            "START_PUMA.bat",
        ]:
            old = ROOT / rel
            if old.exists():
                dst = backup / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, dst)

        allowed_files = [
            "app.py",
            "puma_trader/ui.py",
            "puma_trader/updater.py",
            "puma_trader/__init__.py",
            "PUMA_STOCK_PRO_ICON.svg",
        ]
        for rel in allowed_files:
            source = src / rel
            if not source.exists():
                fail(f"업데이트 파일 누락: {rel}")
            target = ROOT / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        # No-console portable launcher.
        launcher = r'''@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "runtime\pythonw.exe" (
  start "" "%~dp0runtime\pythonw.exe" "%~dp0app.py"
  exit /b 0
)
"runtime\python.exe" app.py
if errorlevel 1 pause
'''
        (ROOT / "START_PUMA.bat").write_text(launcher, encoding="utf-8")

        print("[4/4] 완료")
        print()
        print("v2.9.5 적용 완료.")
        print("이제부터 PUMA 내부의 업데이트 확인/적용 기능을 사용하면 됩니다.")
        print("PUMA를 다시 실행합니다...")

        pythonw = ROOT / "runtime" / "pythonw.exe"
        if pythonw.exists():
            os.spawnv(os.P_NOWAIT, str(pythonw), [str(pythonw), str(APP)])
        else:
            os.spawnv(os.P_NOWAIT, str(RUNTIME), [str(RUNTIME), str(APP)])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(repr(exc))
