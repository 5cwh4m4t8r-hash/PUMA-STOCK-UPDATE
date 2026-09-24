from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


HOST = os.environ.get("PUMA_RELAY_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("PUMA_RELAY_PORT", "8787")))
MAX_DEVICES = max(10, int(os.environ.get("PUMA_RELAY_MAX_DEVICES", "500")))
DEVICE_TTL = max(300, int(os.environ.get("PUMA_RELAY_DEVICE_TTL", "86400")))
PC_ONLINE_SECONDS = max(3, int(os.environ.get("PUMA_RELAY_PC_ONLINE_SECONDS", "5")))
MAX_STATE_BYTES = 2 * 1024 * 1024
MAX_COMMAND_BYTES = 64 * 1024

ALLOWED_COMMANDS = {
    "select_stock",
    "set_chart_mode",
    "order",
    "auto_start",
    "auto_stop",
    "unlock_live",
    "lock_live",
}


@dataclass
class Command:
    id: str
    payload: dict
    created_at: float
    status: str = "pending"
    result: dict = field(default_factory=dict)
    error: str | None = None
    last_delivered_at: float = 0.0


@dataclass
class Device:
    device_id: str
    pc_secret: str
    pair_token: str
    created_at: float
    last_pc_seen: float
    state: dict = field(default_factory=dict)
    commands: dict[str, Command] = field(default_factory=dict)


_LOCK = threading.RLock()
_DEVICES: dict[str, Device] = {}
_FAILED_AUTH: dict[tuple[str, str], list[float]] = {}


def _now() -> float:
    return time.time()


def _clean_locked():
    now = _now()
    stale = [
        device_id
        for device_id, device in _DEVICES.items()
        if now - float(device.last_pc_seen or device.created_at) > DEVICE_TTL
    ]
    for device_id in stale:
        _DEVICES.pop(device_id, None)

    for device in _DEVICES.values():
        old_commands = [
            cid
            for cid, cmd in device.commands.items()
            if now - cmd.created_at > 900
        ]
        for cid in old_commands:
            device.commands.pop(cid, None)

    cutoff = now - 900
    for key, rows in list(_FAILED_AUTH.items()):
        kept = [x for x in rows if x >= cutoff]
        if kept:
            _FAILED_AUTH[key] = kept
        else:
            _FAILED_AUTH.pop(key, None)


class RelayServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "PUMARelay/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args), flush=True)

    @property
    def client_ip(self) -> str:
        try:
            return str(self.client_address[0])
        except Exception:
            return "unknown"

    def _json(self, status: int, obj: dict):
        raw = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self, max_bytes: int) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length < 0 or length > max_bytes:
            raise ValueError("request too large")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("object required")
        return obj

    def _pc_identity(self):
        device_id = str(self.headers.get("X-Puma-Device") or "").strip().lower()
        pc_secret = str(self.headers.get("X-Puma-PC-Secret") or "").strip()
        if len(device_id) != 12 or any(ch not in "0123456789abcdef" for ch in device_id):
            return None, None
        if len(pc_secret) < 32:
            return None, None
        return device_id, pc_secret

    def _mobile_identity(self):
        device_id = str(self.headers.get("X-Puma-Device") or "").strip().lower()
        pair_token = str(self.headers.get("X-Puma-Token") or "").strip()
        return device_id, pair_token

    def _pc_device(self) -> Device | None:
        device_id, pc_secret = self._pc_identity()
        if not device_id:
            return None
        with _LOCK:
            _clean_locked()
            device = _DEVICES.get(device_id)
            if not device:
                return None
            if not secrets.compare_digest(device.pc_secret, pc_secret):
                return None
            device.last_pc_seen = _now()
            return device

    def _mobile_device(self):
        device_id, pair_token = self._mobile_identity()
        key = (self.client_ip, device_id)
        with _LOCK:
            _clean_locked()
            recent = [t for t in _FAILED_AUTH.get(key, []) if _now() - t < 600]
            if len(recent) >= 10:
                return None, HTTPStatus.TOO_MANY_REQUESTS

            device = _DEVICES.get(device_id)
            ok = bool(
                device
                and pair_token
                and len(pair_token) == 6
                and pair_token.isdigit()
                and secrets.compare_digest(device.pair_token, pair_token)
            )
            if not ok:
                recent.append(_now())
                _FAILED_AUTH[key] = recent
                return None, HTTPStatus.UNAUTHORIZED

            _FAILED_AUTH.pop(key, None)
            return device, None

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/healthz":
            with _LOCK:
                _clean_locked()
                count = len(_DEVICES)
            return self._json(200, {"ok": True, "service": "PUMA Relay", "devices": count})

        if path == "/v1/pc/commands":
            device = self._pc_device()
            if not device:
                return self._json(401, {"error": "PC 인증 실패"})
            now = _now()
            rows = []
            with _LOCK:
                for cmd in device.commands.values():
                    if cmd.status != "pending":
                        continue
                    # Redeliver every 5 seconds until the PC posts a result.
                    if cmd.last_delivered_at and now - cmd.last_delivered_at < 5.0:
                        continue
                    cmd.last_delivered_at = now
                    rows.append({"id": cmd.id, "payload": cmd.payload})
                    if len(rows) >= 20:
                        break
            return self._json(200, {"commands": rows})

        if path == "/v1/mobile/state":
            device, error = self._mobile_device()
            if error:
                return self._json(int(error), {"error": "모바일 인증 실패"})
            with _LOCK:
                online = _now() - device.last_pc_seen <= PC_ONLINE_SECONDS
                state = dict(device.state)
                last_seen = device.last_pc_seen
            return self._json(200, {
                "ok": True,
                "pc_online": online,
                "last_pc_seen": last_seen,
                "state": state,
            })

        if path.startswith("/v1/mobile/command/"):
            device, error = self._mobile_device()
            if error:
                return self._json(int(error), {"error": "모바일 인증 실패"})
            cid = path.rsplit("/", 1)[-1]
            with _LOCK:
                cmd = device.commands.get(cid)
                if not cmd:
                    return self._json(404, {"error": "요청을 찾을 수 없습니다."})
                return self._json(200, {
                    "status": cmd.status,
                    "result": cmd.result,
                    "error": cmd.error,
                })

        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/v1/pc/register":
            device_id, pc_secret = self._pc_identity()
            if not device_id:
                return self._json(401, {"error": "PC 인증정보 형식 오류"})
            try:
                body = self._read_json(16 * 1024)
            except Exception:
                return self._json(400, {"error": "잘못된 요청"})
            pair_token = str(body.get("pair_token") or "").strip()
            if len(pair_token) != 6 or not pair_token.isdigit():
                return self._json(400, {"error": "pair token must be 6 digits"})

            with _LOCK:
                _clean_locked()
                existing = _DEVICES.get(device_id)
                if existing and not secrets.compare_digest(existing.pc_secret, pc_secret):
                    if _now() - existing.last_pc_seen < 120:
                        return self._json(409, {"error": "이미 사용 중인 device id"})
                    _DEVICES.pop(device_id, None)

                if not existing:
                    if len(_DEVICES) >= MAX_DEVICES:
                        return self._json(503, {"error": "relay capacity reached"})
                    existing = Device(
                        device_id=device_id,
                        pc_secret=pc_secret,
                        pair_token=pair_token,
                        created_at=_now(),
                        last_pc_seen=_now(),
                    )
                    _DEVICES[device_id] = existing
                existing.pair_token = pair_token
                existing.last_pc_seen = _now()

            return self._json(200, {"ok": True, "device_id": device_id})

        if path == "/v1/pc/state":
            device = self._pc_device()
            if not device:
                return self._json(401, {"error": "PC 인증 실패"})
            try:
                body = self._read_json(MAX_STATE_BYTES)
            except Exception:
                return self._json(400, {"error": "잘못된 state payload"})

            state = body.get("state")
            if not isinstance(state, dict):
                return self._json(400, {"error": "state object required"})
            pair_token = str(body.get("pair_token") or "").strip()
            with _LOCK:
                device.state = state
                device.last_pc_seen = _now()
                if len(pair_token) == 6 and pair_token.isdigit():
                    device.pair_token = pair_token
            return self._json(200, {"ok": True})

        if path.startswith("/v1/pc/result/"):
            device = self._pc_device()
            if not device:
                return self._json(401, {"error": "PC 인증 실패"})
            cid = path.rsplit("/", 1)[-1]
            try:
                body = self._read_json(MAX_COMMAND_BYTES)
            except Exception:
                return self._json(400, {"error": "잘못된 result payload"})

            with _LOCK:
                cmd = device.commands.get(cid)
                if not cmd:
                    return self._json(404, {"error": "요청을 찾을 수 없습니다."})
                status = str(body.get("status") or "")
                if status not in ("done", "error"):
                    return self._json(400, {"error": "invalid status"})
                cmd.status = status
                cmd.result = body.get("result") if isinstance(body.get("result"), dict) else {}
                cmd.error = str(body.get("error")) if body.get("error") else None
            return self._json(200, {"ok": True})

        if path == "/v1/mobile/command":
            device, error = self._mobile_device()
            if error:
                return self._json(int(error), {"error": "모바일 인증 실패"})
            try:
                payload = self._read_json(MAX_COMMAND_BYTES)
            except Exception:
                return self._json(400, {"error": "잘못된 요청"})

            command = str(payload.get("type") or "").strip()
            if command not in ALLOWED_COMMANDS:
                return self._json(400, {"error": "지원하지 않는 명령입니다."})

            cid = uuid.uuid4().hex[:20]
            cmd = Command(id=cid, payload=payload, created_at=_now())
            with _LOCK:
                device.commands[cid] = cmd
            return self._json(202, {"accepted": True, "request_id": cid})

        return self._json(404, {"error": "not found"})


def main():
    server = RelayServer((HOST, PORT), Handler)
    print(f"PUMA Relay listening on http://{HOST}:{PORT}", flush=True)
    print("Terminate TLS at your hosting provider / reverse proxy and expose HTTPS only.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
