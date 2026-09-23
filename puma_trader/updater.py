from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

CURRENT_VERSION = "2.9.4"
CLEAN_BUILD = True


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
        headers={"User-Agent": "PUMA-STOCK-CLEAN/2.9.4"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8-sig"))
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
    raise RuntimeError(
        "CLEAN 배포본에서는 보안을 위해 프로그램 내부 자동 다운로드를 사용하지 않습니다. "
        "새 버전은 확인 후 수동으로 설치하세요."
    )


def stage_and_apply(zip_path: Path, new_version: str) -> None:
    raise RuntimeError(
        "CLEAN 배포본에서는 자기 파일 수정/백그라운드 프로세스 방식의 자동 업데이트를 사용하지 않습니다."
    )
