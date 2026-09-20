from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

CURRENT_VERSION = "1.0.0"


def _vtuple(v: str):
    out = []
    for part in str(v).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str = ""
    sha256: str = ""

    @property
    def newer(self) -> bool:
        return _vtuple(self.version) > _vtuple(CURRENT_VERSION)


def app_root() -> Path:
    return Path(__file__).resolve().parent.parent


def update_config_path() -> Path:
    return app_root() / "config" / "update.json"


def load_update_config() -> dict:
    p = update_config_path()
    if not p.exists():
        return {"manifest_url": "https://raw.githubusercontent.com/5cwh4m4t8r-hash/PUMA-STOCK-UPDATE/main/manifest.json"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"manifest_url": "https://raw.githubusercontent.com/5cwh4m4t8r-hash/PUMA-STOCK-UPDATE/main/manifest.json"}


def save_update_config(data: dict) -> None:
    p = update_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_manifest(manifest_url: str, timeout: int = 12) -> UpdateInfo:
    manifest_url = (manifest_url or "").strip()
    if not manifest_url:
        raise ValueError("업데이트 서버 주소가 아직 설정되지 않았습니다.")
    req = urllib.request.Request(manifest_url, headers={"User-Agent": "PUMA-STOCK-UPDATER/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    data = json.loads(raw.decode("utf-8-sig"))
    version = str(data.get("version") or "").strip()
    url = str(data.get("url") or "").strip()
    if not version or not url:
        raise ValueError("업데이트 정보에 version 또는 url이 없습니다.")
    return UpdateInfo(version=version, url=url, notes=str(data.get("notes") or ""), sha256=str(data.get("sha256") or "").lower())


def download_package(info: UpdateInfo, progress_cb=None) -> Path:
    tmpdir = Path(tempfile.mkdtemp(prefix="puma_update_"))
    target = tmpdir / f"PUMA_STOCK_PRO_v{info.version}.zip"
    req = urllib.request.Request(info.url, headers={"User-Agent": "PUMA-STOCK-UPDATER/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r, target.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)
    if info.sha256:
        h = hashlib.sha256()
        with target.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest().lower() != info.sha256.lower():
            raise ValueError("업데이트 파일 SHA256 검증에 실패했습니다.")
    return target


def stage_and_apply(zip_path: Path, new_version: str) -> None:
    root = app_root()
    worker = root / "_puma_apply_update.py"
    log = root / "update_log.txt"
    # 사용자 설정/인증/로그/가상환경은 업데이트에서 보존한다.
    script = f'''from pathlib import Path\nimport os, shutil, sys, time, zipfile, traceback\nROOT=Path(r"{str(root)}")\nZIP=Path(r"{str(zip_path)}")\nLOG=Path(r"{str(log)}")\nSKIP={{"config", ".venv", "logs", "user_data", "state", "update_log.txt", "_puma_apply_update.py"}}\ndef write(s):\n    with LOG.open("a", encoding="utf-8") as f: f.write(s+"\\n")\ntry:\n    time.sleep(3)\n    stamp=time.strftime("%Y%m%d_%H%M%S")\n    backup=ROOT.parent/(ROOT.name+"_backup_"+stamp)\n    backup.mkdir(parents=True, exist_ok=True)\n    for name in ["app.py","puma_trader","requirements.txt","1_SETUP.bat","2_START_PUMA.vbs","run.bat","setup.ps1","README_KO.txt","PUMA_STOCK_PRO.vbs"]:\n        src=ROOT/name\n        if src.exists():\n            dst=backup/name\n            if src.is_dir(): shutil.copytree(src,dst,dirs_exist_ok=True)\n            else:\n                dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)\n    temp=ROOT.parent/("_puma_update_extract_"+stamp)\n    temp.mkdir(parents=True,exist_ok=True)\n    with zipfile.ZipFile(ZIP,"r") as z: z.extractall(temp)\n    candidates=[p for p in temp.iterdir() if p.is_dir()]\n    srcroot=candidates[0] if len(candidates)==1 and (candidates[0]/"app.py").exists() else temp\n    for item in srcroot.iterdir():\n        if item.name in SKIP: continue\n        dst=ROOT/item.name\n        if item.is_dir(): shutil.copytree(item,dst,dirs_exist_ok=True)\n        else: shutil.copy2(item,dst)\n    write("업데이트 적용 완료: v{new_version}")\n    try:\n        os.startfile(str(ROOT/"2_START_PUMA.vbs"))\n    except Exception as e: write("재실행 실패: "+repr(e))\nexcept Exception:\n    write(traceback.format_exc())\nfinally:\n    try: ZIP.unlink(missing_ok=True)\n    except Exception: pass\n    try: shutil.rmtree(temp, ignore_errors=True)\n    except Exception: pass\n'''
    worker.write_text(script, encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen([sys.executable, str(worker)], cwd=str(root), creationflags=flags, close_fds=True)
