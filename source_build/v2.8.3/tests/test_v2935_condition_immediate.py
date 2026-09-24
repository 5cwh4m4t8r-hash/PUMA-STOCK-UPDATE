import asyncio
import json
from pathlib import Path

from puma_trader.conditions import _fetch_complete_condition_snapshot


class FakeWS:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        if not self.messages:
            await asyncio.sleep(10)
        return json.dumps(self.messages.pop(0), ensure_ascii=False)


def test_manual_snapshot_emits_first_page_before_continuation_finishes():
    ws = FakeWS([
        {
            "trnm": "CNSRREQ",
            "seq": "7",
            "return_code": 0,
            "cont_yn": "Y",
            "next_key": "NEXT1",
            "data": [{"9001": "A005930", "302": "삼성전자"}],
        },
        {
            "trnm": "CNSRREQ",
            "seq": "7",
            "return_code": 0,
            "cont_yn": "N",
            "next_key": "",
            "data": [{"9001": "A000660", "302": "SK하이닉스"}],
        },
    ])
    progress = []

    rows = asyncio.run(
        _fetch_complete_condition_snapshot(
            ws,
            "7",
            timeout=0.2,
            progress_cb=lambda partial: progress.append(list(partial)),
        )
    )

    assert [len(x) for x in progress] == [1, 2]
    assert progress[0] == [("005930", "삼성전자")]
    assert rows == [("005930", "삼성전자"), ("000660", "SK하이닉스")]


def test_multi_condition_has_immediate_initial_partial_signal_and_ui_handler():
    cond = Path("puma_trader/conditions.py").read_text(encoding="utf-8")
    ui = Path("puma_trader/ui.py").read_text(encoding="utf-8")

    assert "initial_partial = Signal(str, str, object)" in cond
    assert "self.initial_partial.emit(seq, st[\"name\"], page_rows)" in cond
    assert "await asyncio.sleep(0.12)" in cond

    assert "thread.initial_partial.connect" in ui
    assert "def on_condition_initial_partial" in ui
    assert "condition_initial_partial_seen" in ui
    assert "즉시수신" in ui


def test_partial_condition_rows_are_not_held_for_background_classification():
    ui = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    start = ui.index("def on_condition_initial_partial")
    end = ui.index("def on_condition_initial_union", start)
    block = ui[start:end]

    assert "_upsert_condition_row" in block
    assert "_queue_candidate_classification" not in block
