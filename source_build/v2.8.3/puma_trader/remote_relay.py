from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QObject, Signal

from .mobile_bridge import MobileBridge


_ALLOWED_COMMANDS = {
    "select_stock",
    "set_chart_mode",
    "order",
    "auto_start",
    "auto_stop",
    "unlock_live",
    "lock_live",
}
_LIVE_COMMANDS = {"order", "auto_start"}


class RemoteRelayClient(QObject):
    """Outbound-only remote mobile relay client.

    The home PC never opens an Internet-facing port. It periodically pushes the
    immutable MobileBridge snapshot to an HTTPS relay and pulls queued mobile
    commands. Commands are still executed by MainWindow._on_mobile_command()
    through MobileBridge.commandReceived, so there is only one order path.
    """

    statusChanged = Signal(str, bool)

    def __init__(self, bridge: MobileBridge, parent=None, *, config_path: str | Path | None = None):
        super().__init__(parent)
        self.bridge = bridge
        root = Path(__file__).resolve().parent.parent
        self.config_path = Path(config_path) if config_path else root / "config" / "mobile_remote.json"
        self.journal_path = root / "config" / "mobile_remote_journal.json"

        cfg = self._load_json(self.config_path)
        self.relay_url = str(cfg.get("relay_url") or "").strip().rstrip("/")
        self.device_id = str(cfg.get("device_id") or secrets.token_hex(6)).lower()
        self.pc_secret = str(cfg.get("pc_secret") or secrets.token_urlsafe(32))
        self._save_config()

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_error = ""
        self._online = False
        self._remote_to_local: dict[str, str] = {}
        self._journal = self._load_json(self.journal_path)
        if not isinstance(self._journal, dict):
            self._journal = {}
        self._prune_journal()

    @staticmethod
    def _load_json(path: Path) -> dict:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _write_json(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _save_config(self):
        try:
            self._write_json(self.config_path, {
                "relay_url": self.relay_url,
                "device_id": self.device_id,
                "pc_secret": self.pc_secret,
            })
        except Exception:
            pass

    def _save_journal(self):
        try:
            self._write_json(self.journal_path, self._journal)
        except Exception:
            pass

    def _prune_journal(self):
        now = time.time()
        self._journal = {
            str(k): v for k, v in self._journal.items()
            if isinstance(v, dict) and now - float(v.get("ts", now)) < 86400
        }
        self._save_journal()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def online(self) -> bool:
        with self._lock:
            return self._online

    @property
    def last_error(self) -> str:
        with self._lock:
            return self._last_error

    def configure(self, relay_url: str):
        relay_url = str(relay_url or "").strip().rstrip("/")
        if relay_url:
            parsed = urlparse(relay_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("외부 Relay 주소는 https:// 주소여야 합니다.")
        self.relay_url = relay_url
        self._save_config()

    def regenerate_identity(self):
        self.device_id = secrets.token_hex(6)
        self.pc_secret = secrets.token_urlsafe(32)
        self._save_config()
        return self.device_id

    def start(self, relay_url: str | None = None):
        if relay_url is not None:
            self.configure(relay_url)
        if not self.relay_url:
            raise ValueError("외부 Relay HTTPS 주소를 먼저 입력하세요.")
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="PUMA-Remote-Relay", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.5)
        self._set_status("외부망 연결 중지", False)

    def _set_status(self, text: str, online: bool):
        with self._lock:
            changed = (self._online != bool(online)) or (self._last_error != str(text))
            self._online = bool(online)
            self._last_error = str(text)
        if changed:
            self.statusChanged.emit(str(text), bool(online))

    def _pc_headers(self) -> dict:
        return {
            "X-Puma-Device": self.device_id,
            "X-Puma-PC-Secret": self.pc_secret,
            "Content-Type": "application/json",
            "User-Agent": "PUMA-STOCK-PRO-REMOTE/1",
        }

    def _post_result(self, session: requests.Session, remote_id: str, row: dict):
        status = str(row.get("status") or "")
        body = {
            "status": status,
            "result": row.get("result") or {},
            "error": row.get("error"),
        }
        r = session.post(
            f"{self.relay_url}/v1/pc/result/{remote_id}",
            headers=self._pc_headers(),
            json=body,
            timeout=5,
        )
        r.raise_for_status()

    def _accept_remote_command(self, session: requests.Session, remote_id: str, payload: dict):
        command = str(payload.get("type") or "").strip()
        if command not in _ALLOWED_COMMANDS:
            self._post_result(session, remote_id, {
                "status": "error",
                "result": {},
                "error": "지원하지 않는 모바일 명령입니다.",
            })
            return

        # Persist BEFORE emitting the Qt command. If the PC dies after an order
        # was sent but before the relay result is posted, a redelivery after
        # restart is blocked instead of risking a duplicate real order.
        old = self._journal.get(remote_id)
        if isinstance(old, dict):
            self._post_result(session, remote_id, {
                "status": "error",
                "result": {},
                "error": "이전 실행 흔적이 있어 중복 실행을 차단했습니다. PC 주문/로그를 확인하세요.",
            })
            return

        if command in _LIVE_COMMANDS and not self.bridge.live_unlocked:
            self._post_result(session, remote_id, {
                "status": "error",
                "result": {},
                "error": "모바일 실전 잠금을 먼저 해제하세요.",
            })
            return

        self._journal[remote_id] = {"ts": time.time(), "status": "claimed", "type": command}
        self._save_journal()
        local_id = self.bridge.queue_command(payload)
        self._remote_to_local[remote_id] = local_id

    def _sync_command_results(self, session: requests.Session):
        finished = []
        for remote_id, local_id in list(self._remote_to_local.items()):
            row = self.bridge.command_status(local_id)
            if not row or row.get("status") not in ("done", "error"):
                continue
            self._post_result(session, remote_id, row)
            item = self._journal.get(remote_id)
            if isinstance(item, dict):
                item["status"] = str(row.get("status"))
                item["ts"] = time.time()
                self._save_journal()
            finished.append(remote_id)
        for remote_id in finished:
            self._remote_to_local.pop(remote_id, None)

    def _run(self):
        session = requests.Session()
        last_registered_token = ""
        state_due = 0.0
        command_due = 0.0
        backoff = 1.0

        while not self._stop.is_set():
            try:
                now = time.time()
                token = str(self.bridge.token)

                if token != last_registered_token:
                    r = session.post(
                        f"{self.relay_url}/v1/pc/register",
                        headers=self._pc_headers(),
                        json={
                            "pair_token": token,
                            "version": "1",
                            "device_name": "PUMA STOCK PRO",
                        },
                        timeout=6,
                    )
                    r.raise_for_status()
                    last_registered_token = token

                if now >= state_due:
                    r = session.post(
                        f"{self.relay_url}/v1/pc/state",
                        headers=self._pc_headers(),
                        json={
                            "pair_token": token,
                            "mobile_live_unlocked": bool(self.bridge.live_unlocked),
                            "state": self.bridge.state(),
                            "ts": now,
                        },
                        timeout=6,
                    )
                    r.raise_for_status()
                    state_due = now + 0.75

                if now >= command_due:
                    r = session.get(
                        f"{self.relay_url}/v1/pc/commands",
                        headers=self._pc_headers(),
                        timeout=5,
                    )
                    r.raise_for_status()
                    data = r.json() if r.content else {}
                    for item in list(data.get("commands") or []):
                        remote_id = str(item.get("id") or "")
                        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                        if not remote_id or remote_id in self._remote_to_local:
                            continue
                        self._accept_remote_command(session, remote_id, payload)
                    command_due = now + 0.25

                self._sync_command_results(session)
                self._set_status("외부망 연결됨", True)
                backoff = 1.0
                self._stop.wait(0.10)

            except Exception as exc:
                self._set_status(f"외부망 연결 대기: {exc}", False)
                self._stop.wait(backoff)
                backoff = min(8.0, backoff * 1.7)
                last_registered_token = ""

        try:
            session.close()
        except Exception:
            pass
