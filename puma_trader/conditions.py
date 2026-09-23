from __future__ import annotations

import asyncio
import json
from typing import Any, Iterable

from PySide6.QtCore import QThread, Signal

try:
    from websockets.asyncio.client import connect as ws_connect
except ImportError:  # websockets 13 fallback
    from websockets import connect as ws_connect


class ConditionError(RuntimeError):
    pass


def normalize_code(raw: Any) -> str:
    text = str(raw or "").strip()
    if text.startswith("A") and len(text) >= 7:
        text = text[1:]
    # REST 실시간 종목코드 suffix가 붙는 경우 기본 6자리만 사용
    if "_" in text:
        text = text.split("_", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else text


def parse_condition_list(data: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not isinstance(data, list):
        return out
    for item in data:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((str(item[0]).strip(), str(item[1]).strip()))
        elif isinstance(item, dict):
            seq = item.get("seq") or item.get("id") or item.get("0")
            name = item.get("name") or item.get("1")
            if seq is not None and name is not None:
                out.append((str(seq).strip(), str(name).strip()))
    return out


def parse_snapshot_codes(data: Any) -> list[tuple[str, str]]:
    """CNSRREQ 초기 검색 결과를 [(code, name), ...] 형태로 정규화."""
    out: list[tuple[str, str]] = []
    if not isinstance(data, list):
        return out
    for item in data:
        if isinstance(item, dict):
            raw = item.get("jmcode") or item.get("9001") or item.get("stk_cd")
            name = item.get("302") or item.get("stk_nm") or item.get("name") or item.get("jongmok_nm") or ""
            if raw:
                # 일부 응답은 세미콜론 구분 종목코드를 한 문자열에 담을 수 있음
                for token in str(raw).replace(",", ";").split(";"):
                    code = normalize_code(token)
                    if code:
                        out.append((code, str(name).strip()))
        elif isinstance(item, str):
            for token in item.replace(",", ";").split(";"):
                code = normalize_code(token)
                if code:
                    out.append((code, ""))
    # 순서 보존 중복 제거
    seen = set()
    unique = []
    for code, name in out:
        if code not in seen:
            seen.add(code)
            unique.append((code, name))
    return unique


def parse_realtime_events(message: dict[str, Any]) -> list[tuple[str, str]]:
    """REAL 조건검색 이벤트 -> [("I"|"D", code), ...]."""
    events: list[tuple[str, str]] = []
    data = message.get("data", [])
    if not isinstance(data, list):
        return events
    for item in data:
        if not isinstance(item, dict):
            continue
        values = item.get("values") if isinstance(item.get("values"), dict) else item
        action = str(values.get("843") or values.get("insert_delete") or "").strip().upper()
        code = normalize_code(values.get("9001") or values.get("jmcode") or item.get("name"))
        if action in ("I", "D") and code:
            events.append((action, code))
    return events


async def _recv_non_ping(ws):
    while True:
        raw = await ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            msg = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            msg = raw
        is_ping = (isinstance(msg, str) and msg.strip().upper() == "PING") or (
            isinstance(msg, dict) and str(msg.get("trnm", "")).upper() == "PING"
        )
        if is_ping:
            await ws.send(json.dumps(msg, ensure_ascii=False) if not isinstance(msg, str) else msg)
            continue
        return msg


async def _login(ws, token: str):
    await ws.send(json.dumps({"trnm": "LOGIN", "token": token}, ensure_ascii=False))
    msg = await _recv_non_ping(ws)
    if not isinstance(msg, dict) or str(msg.get("trnm", "")).upper() != "LOGIN":
        raise ConditionError("키움 WebSocket LOGIN 응답을 받지 못했습니다.")
    if int(msg.get("return_code", 0) or 0) != 0:
        raise ConditionError(str(msg.get("return_msg", "WebSocket 로그인 실패")))


def _ws_url(real: bool) -> str:
    host = "wss://api.kiwoom.com:10000" if real else "wss://mockapi.kiwoom.com:10000"
    return host + "/api/dostk/websocket"


async def _fetch_condition_list(token: str, real: bool) -> list[tuple[str, str]]:
    async with ws_connect(_ws_url(real), ping_interval=None, open_timeout=10) as ws:
        await _login(ws, token)
        await ws.send(json.dumps({"trnm": "CNSRLST"}, ensure_ascii=False))
        while True:
            msg = await asyncio.wait_for(_recv_non_ping(ws), timeout=10)
            if isinstance(msg, dict) and str(msg.get("trnm", "")).upper() == "CNSRLST":
                if int(msg.get("return_code", 0) or 0) != 0:
                    raise ConditionError(str(msg.get("return_msg", "조건식 목록 조회 실패")))
                return parse_condition_list(msg.get("data"))


def fetch_condition_list(token: str, real: bool) -> list[tuple[str, str]]:
    return asyncio.run(_fetch_condition_list(token, real))


class ConditionStreamThread(QThread):
    status = Signal(str)
    error = Signal(str)
    snapshot = Signal(object)  # list[(code,name)]
    entered = Signal(str, str)
    exited = Signal(str)

    def __init__(self, token: str, real: bool, seq: str, parent=None):
        super().__init__(parent)
        self.token = token
        self.real = real
        self.seq = str(seq).strip()
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            if not self._stop_requested:
                self.error.emit(str(exc))

    async def _run(self):
        url = _ws_url(self.real)
        async with ws_connect(url, ping_interval=None, open_timeout=10) as ws:
            await _login(ws, self.token)
            self.status.emit("영웅문 조건검색 WebSocket 연결됨")
            req = {"trnm": "CNSRREQ", "seq": self.seq, "search_type": "1", "stex_tp": "K"}
            await ws.send(json.dumps(req, ensure_ascii=False))

            while not self._stop_requested:
                try:
                    msg = await asyncio.wait_for(_recv_non_ping(ws), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if not isinstance(msg, dict):
                    continue
                trnm = str(msg.get("trnm", "")).upper()
                if trnm == "CNSRREQ":
                    if int(msg.get("return_code", 0) or 0) != 0:
                        raise ConditionError(str(msg.get("return_msg", "실시간 조건검색 시작 실패")))
                    rows = parse_snapshot_codes(msg.get("data"))
                    self.snapshot.emit(rows)
                    self.status.emit(f"조건검색 실행 중 · 초기 {len(rows)}종목")
                elif trnm == "REAL":
                    for action, code in parse_realtime_events(msg):
                        if action == "I":
                            self.entered.emit(code, "")
                        elif action == "D":
                            self.exited.emit(code)

            try:
                await ws.send(json.dumps({"trnm": "CNSRCLR", "seq": self.seq}, ensure_ascii=False))
            except Exception:
                pass
            self.status.emit("영웅문 조건검색 중지")


PUMA_DEFAULT_CONDITION_NAMES = (
    "단타단타(시원놈)",
    "5분봉_단타(시원놈)",
    "단타1",
    "시초가1번",
    "시초가1-1번",
    "시초가2번",
    "시초가멀티",
)


def normalize_condition_name(name: str) -> str:
    text = str(name or "").strip()
    for ch in ("★", "☆", " ", "\t"):
        text = text.replace(ch, "")
    return text


def select_puma_conditions(
    rows: list[tuple[str, str]],
    configured_names: Iterable[str] | None = None,
) -> list[tuple[str, str]]:
    """Return the configured PUMA condition bundle in server-list order.

    Searcher overlap is not a requirement. Every selected condition contributes
    its own candidates to one union pool.
    """
    wanted = tuple(configured_names or PUMA_DEFAULT_CONDITION_NAMES)
    wanted_norm = {normalize_condition_name(x) for x in wanted if str(x).strip()}
    selected = []
    seen = set()
    for seq, name in rows or []:
        key = normalize_condition_name(name)
        if key in wanted_norm and str(seq).strip() not in seen:
            seen.add(str(seq).strip())
            selected.append((str(seq).strip(), str(name).strip()))
    return selected


def update_candidate_source(
    candidates: dict[str, dict],
    *,
    seq: str,
    condition_name: str,
    code: str,
    stock_name: str = "",
    active: bool,
    entry_event: bool,
    now: str,
) -> dict:
    """Merge one condition's state into the union candidate pool.

    A stock from a single searcher is fully eligible. source_count is metadata
    only and must never be used as a buy requirement.
    """
    code = normalize_code(code)
    item = candidates.setdefault(code, {
        "name": stock_name or code,
        "active": False,
        "entered_at": now or "-",
        "entry_event": False,
        "classification": "분석중",
        "class_detail": "-",
        "sources": {},
    })
    if stock_name and stock_name != code:
        item["name"] = stock_name
    sources = item.setdefault("sources", {})
    skey = str(seq).strip()
    src = dict(sources.get(skey) or {})
    src["name"] = str(condition_name or skey)
    src["active"] = bool(active)
    src["entry_event"] = bool(entry_event) if active else False
    if active:
        src["entered_at"] = now
        if not item.get("entered_at") or item.get("entered_at") == "-":
            item["entered_at"] = now
    sources[skey] = src

    active_sources = [x for x in sources.values() if x.get("active")]
    item["active"] = bool(active_sources)
    item["entry_event"] = any(x.get("active") and x.get("entry_event") for x in sources.values())
    item["source_count"] = len(active_sources)
    item["seen_source_count"] = len(sources)
    item["source_names"] = [str(x.get("name") or "") for x in active_sources]
    return item


class MultiConditionStreamThread(QThread):
    """Run up to 10 Kiwoom real-time condition searches on one WebSocket session."""

    status = Signal(str)
    error = Signal(str)
    snapshot = Signal(str, str, object)       # seq, condition_name, rows
    entered = Signal(str, str, str, str)     # seq, condition_name, code, stock_name
    exited = Signal(str, str, str)            # seq, condition_name, code

    def __init__(self, token: str, real: bool, conditions: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.token = token
        self.real = real
        self.conditions = [(str(seq).strip(), str(name).strip()) for seq, name in conditions][:10]
        self.names = {seq: name for seq, name in self.conditions}
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            if not self._stop_requested:
                self.error.emit(str(exc))

    async def _run(self):
        if not self.conditions:
            raise ConditionError("실행할 PUMA 조건식이 없습니다.")
        url = _ws_url(self.real)
        async with ws_connect(url, ping_interval=None, open_timeout=10) as ws:
            await _login(ws, self.token)
            self.status.emit(f"PUMA 조건검색 {len(self.conditions)}개 WebSocket 연결됨")

            for seq, name in self.conditions:
                await ws.send(json.dumps({
                    "trnm": "CNSRREQ",
                    "seq": seq,
                    "search_type": "1",
                    "stex_tp": "K",
                }, ensure_ascii=False))

            while not self._stop_requested:
                try:
                    msg = await asyncio.wait_for(_recv_non_ping(ws), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if not isinstance(msg, dict):
                    continue
                trnm = str(msg.get("trnm", "")).upper()
                if trnm == "CNSRREQ":
                    seq = str(msg.get("seq", "")).strip()
                    name = self.names.get(seq, seq)
                    if int(msg.get("return_code", 0) or 0) != 0:
                        self.error.emit(f"[{seq}] {name}: {msg.get('return_msg', '실시간 조건검색 시작 실패')}")
                        continue
                    rows = parse_snapshot_codes(msg.get("data"))
                    self.snapshot.emit(seq, name, rows)
                    self.status.emit(f"[{seq}] {name} 실행 · 초기 {len(rows)}종목")
                elif trnm == "REAL":
                    data = msg.get("data", [])
                    if not isinstance(data, list):
                        continue
                    for row in data:
                        if not isinstance(row, dict):
                            continue
                        values = row.get("values") if isinstance(row.get("values"), dict) else row
                        seq = str(values.get("841") or "").strip()
                        action = str(values.get("843") or "").strip().upper()
                        code = normalize_code(values.get("9001") or row.get("item") or "")
                        if not seq or not code or action not in ("I", "D"):
                            continue
                        name = self.names.get(seq, seq)
                        if action == "I":
                            self.entered.emit(seq, name, code, "")
                        else:
                            self.exited.emit(seq, name, code)

            for seq, _ in self.conditions:
                try:
                    await ws.send(json.dumps({"trnm": "CNSRCLR", "seq": seq}, ensure_ascii=False))
                except Exception:
                    pass
            self.status.emit("PUMA 다중 조건검색 중지")
