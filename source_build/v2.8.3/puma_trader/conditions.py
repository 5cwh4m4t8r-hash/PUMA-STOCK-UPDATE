from __future__ import annotations

import asyncio
import json
import re
import unicodedata
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


class ConditionListThread(QThread):
    loaded = Signal(object)
    error = Signal(str)

    def __init__(self, token: str, real: bool, parent=None):
        super().__init__(parent)
        self.token = token
        self.real = real

    def run(self):
        try:
            self.loaded.emit(fetch_condition_list(self.token, self.real))
        except Exception as exc:
            self.error.emit(str(exc))


async def _fetch_complete_condition_snapshot(
    ws,
    seq: str,
    *,
    timeout: float = 6.0,
    max_pages: int = 20,
) -> list[tuple[str, str]]:
    """Fetch every page of one current condition result."""
    merged: dict[str, str] = {}
    cont_yn = "N"
    next_key = ""

    for _ in range(max_pages):
        await ws.send(json.dumps({
            "trnm": "CNSRREQ",
            "seq": str(seq),
            "search_type": "0",
            "stex_tp": "K",
            "cont_yn": cont_yn,
            "next_key": next_key,
        }, ensure_ascii=False))

        msg = await asyncio.wait_for(_recv_non_ping(ws), timeout=timeout)
        if not isinstance(msg, dict) or str(msg.get("trnm", "")).upper() != "CNSRREQ":
            raise ConditionError(f"[{seq}] 조건검색 초기 응답 형식 불일치")
        response_seq = str(msg.get("seq", "")).strip()
        if response_seq and response_seq != str(seq):
            raise ConditionError(f"[{seq}] 조건검색 응답 번호 불일치({response_seq})")
        if int(msg.get("return_code", 0) or 0) != 0:
            raise ConditionError(str(msg.get("return_msg", "조건검색 초기조회 실패")))

        for code, stock_name in parse_snapshot_codes(msg.get("data")):
            if code:
                merged[code] = stock_name or merged.get(code, code)

        cont_yn = str(msg.get("cont_yn") or msg.get("cont-yn") or "N").strip().upper()
        next_key = str(msg.get("next_key") or msg.get("next-key") or "").strip()
        if cont_yn != "Y" or not next_key:
            break
        await asyncio.sleep(0.05)

    return [(code, merged[code]) for code in merged]


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
            self.status.emit("현재 종목 조회 중...")

            # 먼저 일반조회로 전체 페이지를 한 번에 가져온다.
            rows = await _fetch_complete_condition_snapshot(ws, self.seq)
            if self._stop_requested:
                return
            self.snapshot.emit(rows)
            self.status.emit(f"현재 {len(rows)}종목 · 실시간 감시 연결 중...")

            # 이후 편입/이탈만 실시간으로 감시한다.
            await ws.send(json.dumps({
                "trnm": "CNSRREQ",
                "seq": self.seq,
                "search_type": "1",
                "stex_tp": "K",
            }, ensure_ascii=False))

            registered = False
            register_attempts = 1
            last_register = asyncio.get_running_loop().time()

            while not self._stop_requested:
                try:
                    msg = await asyncio.wait_for(_recv_non_ping(ws), timeout=1.0)
                except asyncio.TimeoutError:
                    if (
                        not registered
                        and register_attempts < 3
                        and asyncio.get_running_loop().time() - last_register >= 2.0
                    ):
                        await ws.send(json.dumps({
                            "trnm": "CNSRREQ",
                            "seq": self.seq,
                            "search_type": "1",
                            "stex_tp": "K",
                        }, ensure_ascii=False))
                        register_attempts += 1
                        last_register = asyncio.get_running_loop().time()
                    continue

                if not isinstance(msg, dict):
                    continue
                trnm = str(msg.get("trnm", "")).upper()
                if trnm == "CNSRREQ":
                    if int(msg.get("return_code", 0) or 0) != 0:
                        raise ConditionError(str(msg.get("return_msg", "실시간 조건검색 시작 실패")))
                    registered = True
                    # 등록 응답에 현재 종목이 포함되면 누락분만 추가된다.
                    for code, name in parse_snapshot_codes(msg.get("data")):
                        self.entered.emit(code, name)
                    self.status.emit(f"현재 {len(rows)}종목 · 실시간 감시 중")
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

# 사용자 지정 단타 후보 공급기 묶음. 하나의 조건식이 아니라 아래 전체의 합집합을 쓴다.
PUMA_DANTA_CONDITION_NAMES = PUMA_DEFAULT_CONDITION_NAMES


def normalize_condition_name(name: str) -> str:
    """Canonical condition name used for PUMA bundle matching.

    Kiwoom/user-saved names can differ only by spaces, underscores, brackets,
    stars, hyphens or full-width punctuation.  Those formatting differences
    must not make one of the configured day-searchers appear as 'missing'.
    """
    text = unicodedata.normalize("NFKC", str(name or "")).strip().lower()
    # Keep only Korean syllables/jamo, ASCII letters and digits.
    # Examples below all become the same key:
    #   5분봉_단타(시원놈)
    #   5분봉 단타 (시원놈)
    #   5분봉-단타-시원놈
    return re.sub(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]+", "", text)


def is_puma_danta_condition(name: str) -> bool:
    key = normalize_condition_name(name)
    return key in {normalize_condition_name(x) for x in PUMA_DANTA_CONDITION_NAMES}


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
    initial_union = Signal(object)              # list[{seq,name,rows}] emitted once
    snapshot = Signal(str, str, object)       # realtime registration delta rows
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

    async def _collect_initial_union(self, ws) -> list[dict]:
        """Pipeline all initial condition queries, then emit one complete union payload."""
        loop = asyncio.get_running_loop()
        states: dict[str, dict] = {
            seq: {
                "name": name,
                "merged": {},
                "cont_yn": "N",
                "next_key": "",
                "attempts": 0,
                "last_sent": 0.0,
                "done": False,
                "ok": False,
            }
            for seq, name in self.conditions
        }

        async def send_request(seq: str):
            st = states[seq]
            await ws.send(json.dumps({
                "trnm": "CNSRREQ",
                "seq": seq,
                "search_type": "0",
                "stex_tp": "K",
                "cont_yn": st["cont_yn"],
                "next_key": st["next_key"],
            }, ensure_ascii=False))
            st["attempts"] += 1
            st["last_sent"] = loop.time()

        # One connection, multiple seq requests in flight. This avoids waiting for
        # searcher A to finish before B can even start.
        for seq, _ in self.conditions:
            if self._stop_requested:
                break
            await send_request(seq)
            await asyncio.sleep(0.04)

        while not self._stop_requested and not all(st["done"] for st in states.values()):
            try:
                msg = await asyncio.wait_for(_recv_non_ping(ws), timeout=0.5)
            except asyncio.TimeoutError:
                now = loop.time()
                for seq, st in states.items():
                    if st["done"] or now - float(st["last_sent"]) < 2.5:
                        continue
                    if st["attempts"] < 3:
                        self.status.emit(
                            f"[{seq}] {st['name']} 초기조회 재시도 {st['attempts']+1}/3"
                        )
                        await send_request(seq)
                        await asyncio.sleep(0.03)
                    else:
                        st["done"] = True
                        st["ok"] = False
                        self.error.emit(f"[{seq}] {st['name']}: 초기 조건검색 응답 시간초과")
                continue

            if not isinstance(msg, dict) or str(msg.get("trnm", "")).upper() != "CNSRREQ":
                continue

            seq = str(msg.get("seq", "")).strip()
            if seq not in states:
                continue
            st = states[seq]
            if st["done"]:
                continue

            if int(msg.get("return_code", 0) or 0) != 0:
                if st["attempts"] < 3:
                    self.status.emit(
                        f"[{seq}] {st['name']} 초기조회 오류 재시도 {st['attempts']+1}/3"
                    )
                    await send_request(seq)
                    continue
                st["done"] = True
                st["ok"] = False
                self.error.emit(
                    f"[{seq}] {st['name']}: {msg.get('return_msg', '초기 조건검색 실패')}"
                )
                continue

            for code, stock_name in parse_snapshot_codes(msg.get("data")):
                if code:
                    st["merged"][code] = stock_name or st["merged"].get(code, code)

            cont_yn = str(msg.get("cont_yn") or msg.get("cont-yn") or "N").strip().upper()
            next_key = str(msg.get("next_key") or msg.get("next-key") or "").strip()
            if cont_yn == "Y" and next_key:
                st["cont_yn"] = "Y"
                st["next_key"] = next_key
                st["attempts"] = 0
                await send_request(seq)
            else:
                st["done"] = True
                st["ok"] = True

        payload = []
        for seq, name in self.conditions:
            st = states[seq]
            rows = [(code, st["merged"][code]) for code in st["merged"]]
            payload.append({"seq": seq, "name": name, "rows": rows, "ok": bool(st["ok"])})
        return payload

    async def _run(self):
        if not self.conditions:
            raise ConditionError("실행할 PUMA 조건식이 없습니다.")
        url = _ws_url(self.real)
        async with ws_connect(url, ping_interval=None, open_timeout=10) as ws:
            await _login(ws, self.token)
            self.status.emit(f"PUMA 조건검색 {len(self.conditions)}개 WebSocket 연결됨")

            # 1) 7개 일반조회를 한 WebSocket에서 파이프라인 처리한다.
            #    UI에는 검색기별로 찔끔찔끔 보내지 않고 전부 수집한 뒤 한 번만 전달한다.
            initial_payload = await self._collect_initial_union(ws)
            if self._stop_requested:
                return
            self.initial_union.emit(initial_payload)
            initial_ok = sum(1 for x in initial_payload if x.get("ok"))
            initial_count = len({
                code
                for x in initial_payload
                for code, _ in (x.get("rows") or [])
            })
            self.status.emit(
                f"PUMA 초기 통합조회 {initial_ok}/{len(self.conditions)} 완료 · 합집합 {initial_count}종목"
            )

            # 2) 초기 합집합을 만든 뒤 같은 7개 조건을 실시간 편입/이탈로 등록한다.
            #    한꺼번에 패킷을 몰아 보내지 않고 간격을 둬 서버 등록 누락을 줄인다.
            live_attempts = {seq: 0 for seq, _ in self.conditions}
            live_sent_at = {}
            live_registered: set[str] = set()

            async def send_live(seq: str):
                await ws.send(json.dumps({
                    "trnm": "CNSRREQ",
                    "seq": seq,
                    "search_type": "1",
                    "stex_tp": "K",
                }, ensure_ascii=False))
                live_attempts[seq] = live_attempts.get(seq, 0) + 1
                live_sent_at[seq] = asyncio.get_running_loop().time()

            for seq, _ in self.conditions:
                if self._stop_requested:
                    break
                await send_live(seq)
                await asyncio.sleep(0.22)

            while not self._stop_requested:
                try:
                    msg = await asyncio.wait_for(_recv_non_ping(ws), timeout=1.0)
                except asyncio.TimeoutError:
                    # 등록 응답이 오지 않은 조건식만 최대 3회 재등록한다.
                    now_mono = asyncio.get_running_loop().time()
                    for seq, name in self.conditions:
                        if seq in live_registered or live_attempts.get(seq, 0) >= 3:
                            continue
                        if now_mono - float(live_sent_at.get(seq, 0.0) or 0.0) >= 2.0:
                            self.status.emit(
                                f"[{seq}] {name} 실시간 등록 재시도 {live_attempts.get(seq, 0)+1}/3"
                            )
                            await send_live(seq)
                            await asyncio.sleep(0.18)
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
                    live_registered.add(seq)
                    # 초기 일반조회 뒤 등록 사이에 새로 편입된 종목이 있으면 합집합에 추가한다.
                    rows = parse_snapshot_codes(msg.get("data"))
                    if rows:
                        self.snapshot.emit(seq, name, rows)
                    self.status.emit(
                        f"[{seq}] {name} 실시간 등록 완료 · 전체 {len(live_registered)}/{len(self.conditions)}"
                    )
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
