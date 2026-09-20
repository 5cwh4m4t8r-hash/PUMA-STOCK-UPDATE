from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CRED_PATH = CONFIG_DIR / "kiwoom_credentials.dat"


class CredentialError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _crypt_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialError("Windows에서만 보안 저장을 사용할 수 있습니다.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    inp, keep = _blob(data)
    out = DATA_BLOB()
    # CRYPTPROTECT_UI_FORBIDDEN: 사용자 팝업 없이 현재 Windows 사용자 계정에 귀속해 암호화
    if not crypt32.CryptProtectData(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)):
        raise CredentialError(f"Windows DPAPI 암호화 실패: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _crypt_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialError("Windows에서만 보안 저장을 사용할 수 있습니다.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    inp, keep = _blob(data)
    out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)):
        raise CredentialError(f"Windows DPAPI 복호화 실패: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def save_credentials(app_key: str, app_secret: str, environment: str, auto_connect: bool) -> None:
    app_key = (app_key or "").strip()
    app_secret = (app_secret or "").strip()
    if not app_key or not app_secret:
        raise CredentialError("App Key와 App Secret을 모두 입력하세요.")
    payload = {
        "app_key": app_key,
        "app_secret": app_secret,
        "environment": "REAL" if environment == "REAL" else "MOCK",
        "auto_connect": bool(auto_connect),
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    enc = _crypt_protect(raw)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CRED_PATH.write_bytes(enc)


def load_credentials() -> dict:
    if not CRED_PATH.exists():
        return {}
    try:
        raw = _crypt_unprotect(CRED_PATH.read_bytes())
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            "app_key": str(data.get("app_key") or ""),
            "app_secret": str(data.get("app_secret") or ""),
            "environment": "REAL" if str(data.get("environment") or "MOCK").upper() == "REAL" else "MOCK",
            "auto_connect": bool(data.get("auto_connect", False)),
        }
    except Exception as exc:
        raise CredentialError(str(exc)) from exc


def clear_credentials() -> None:
    try:
        CRED_PATH.unlink(missing_ok=True)
    except Exception as exc:
        raise CredentialError(str(exc)) from exc
