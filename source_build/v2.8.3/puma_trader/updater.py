from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

CURRENT_VERSION = "2.9.42"


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


DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/5cwh4m4t8r-hash/PUMA-STOCK-UPDATE/main/manifest.json"


def load_update_config() -> dict:
    p = update_config_path()
    if not p.exists():
        return {"manifest_url": DEFAULT_MANIFEST_URL}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        url = str(data.get("manifest_url") or "").strip()
        if not url:
            data["manifest_url"] = DEFAULT_MANIFEST_URL
        return data
    except Exception:
        return {"manifest_url": DEFAULT_MANIFEST_URL}


def save_update_config(data: dict) -> None:
    p = update_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_manifest(manifest_url: str, timeout: int = 12) -> UpdateInfo:
    manifest_url = (manifest_url or DEFAULT_MANIFEST_URL).strip()
    req = urllib.request.Request(
        manifest_url,
        headers={"User-Agent": f"PUMA-STOCK-UPDATER/{CURRENT_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read()
    data = json.loads(raw.decode("utf-8-sig"))
    version = str(data.get("version") or "").strip()
    url = str(data.get("url") or "").strip()
    if not version or not url:
        raise ValueError("업데이트 정보에 version 또는 url이 없습니다.")
    return UpdateInfo(
        version=version,
        url=url,
        notes=str(data.get("notes") or ""),
        sha256=str(data.get("sha256") or "").lower(),
    )


def download_package(info: UpdateInfo, progress_cb=None) -> Path:
    tmpdir = Path(tempfile.mkdtemp(prefix="puma_update_"))
    target = tmpdir / f"PUMA_STOCK_PRO_v{info.version}.zip"
    req = urllib.request.Request(
        info.url,
        headers={"User-Agent": f"PUMA-STOCK-UPDATER/{CURRENT_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=60) as res, target.open("wb") as f:
        total = int(res.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = res.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)

    if not info.sha256:
        raise ValueError("보안상 SHA256이 없는 업데이트는 적용하지 않습니다.")

    h = hashlib.sha256()
    with target.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    if actual != info.sha256.lower():
        raise ValueError("업데이트 파일 SHA256 검증에 실패했습니다.")
    return target


def _extract_safe(zip_path: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            name = str(member.filename or "").replace("\\", "/")
            path = Path(name)
            if not name or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"안전하지 않은 업데이트 경로: {name}")
            target = (dest / path).resolve()
            if target != dest_resolved and dest_resolved not in target.parents:
                raise ValueError(f"업데이트 경로가 프로그램 폴더를 벗어납니다: {name}")
        zf.extractall(dest)


def _source_root(extracted: Path) -> Path:
    if (extracted / "app.py").exists():
        return extracted
    dirs = [p for p in extracted.iterdir() if p.is_dir()]
    if len(dirs) == 1 and (dirs[0] / "app.py").exists():
        return dirs[0]
    raise ValueError("업데이트 패키지에서 app.py를 찾지 못했습니다.")


def stage_and_apply(zip_path: Path, new_version: str) -> None:
    """Apply a verified source update in the current process.

    No helper script, VBS, detached process, PowerShell, or background self-updater
    is created. Runtime/config/user data are never replaced by an update package.
    """
    root = app_root()
    temp = Path(tempfile.mkdtemp(prefix="puma_apply_"))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = root.parent / f"{root.name}_backup_{stamp}"

    allowed = {
        "app.py",
        "puma_trader",
        "requirements.txt",
        "PUMA_STOCK_PRO_ICON.svg",
        "README_KO.txt",
        "SECURITY_NOTES.txt",
        "PUMA_STOCK_PRO.exe",
        "PUMA_STOCK_PRO.ico",
    }
    preserve = {"config", "runtime", ".venv", "logs", "user_data", "state"}

    try:
        _extract_safe(Path(zip_path), temp)
        src = _source_root(temp)

        package_names = {p.name for p in src.iterdir()}
        if "puma_trader" not in package_names:
            raise ValueError("업데이트 패키지에 puma_trader가 없습니다.")

        backup.mkdir(parents=True, exist_ok=True)
        for name in allowed:
            current = root / name
            if not current.exists():
                continue
            dst = backup / name
            if current.is_dir():
                shutil.copytree(current, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(current, dst)

        for item in src.iterdir():
            if item.name in preserve:
                continue
            if item.name not in allowed:
                continue
            dst = root / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)

        log = root / "update_log.txt"
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} v{new_version} in-process update applied\n")
    except Exception:
        # If an apply fails after backup creation, restore the source files.
        if backup.exists():
            for item in backup.iterdir():
                dst = root / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst)
        raise
    finally:
        shutil.rmtree(temp, ignore_errors=True)
        try:
            Path(zip_path).unlink(missing_ok=True)
            Path(zip_path).parent.rmdir()
        except Exception:
            pass


def install_marker_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "PUMA_STOCK_PRO" / "install_path.txt"


def write_install_marker(root: Path | None = None) -> Path:
    root = Path(root or app_root()).resolve()
    marker = install_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(root), encoding="utf-8")
    return marker


def restart_app(app_path: Path | None = None, root_path: Path | None = None) -> int:
    """Start a fresh PUMA process, then let the caller close the old GUI.

    QProcess.startDetached is used instead of os.execv because os.execv is not
    reliable for a running Windows/PySide GUI process. No helper/VBS/PowerShell
    file is created.
    """
    from PySide6.QtCore import QProcess

    root = Path(root_path or app_root()).resolve()
    app = Path(app_path or (root / "app.py")).resolve()
    if not app.exists():
        raise FileNotFoundError("app.py를 찾을 수 없습니다.")

    write_install_marker(root)
    result = QProcess.startDetached(sys.executable, [str(app)], str(root))
    if isinstance(result, tuple):
        started, pid = result
    else:
        started, pid = bool(result), 0
    if not started:
        raise RuntimeError("새 PUMA 프로세스를 시작하지 못했습니다.")
    return int(pid or 0)
