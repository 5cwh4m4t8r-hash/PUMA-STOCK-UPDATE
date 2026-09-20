import socket
import time
from pathlib import Path

import requests

from puma_trader.mobile_bridge import MobileBridge


def free_port():
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.bind(("127.0.0.1",0))
    port=s.getsockname()[1]
    s.close()
    return port


def wait_ping(base):
    for _ in range(40):
        try:
            if requests.get(base+"/api/ping",timeout=.3).ok:
                return
        except Exception:
            time.sleep(.03)
    raise AssertionError("mobile bridge did not start")


def test_order_and_auto_use_same_single_persistent_unlock(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    port=free_port()
    bridge.publish({
        "version":"2.8.2",
        "auto":{"enabled":False,"scope":"ALL","settings":{}},
        "selected":{"code":"001520","name":"동양","chart":{"candles":[]}},
    })
    bridge.start(port)
    base=f"http://127.0.0.1:{port}"
    headers={"X-Puma-Token":bridge.token}
    try:
        wait_ping(base)

        order_locked=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"order","side":"BUY","code":"001520","qty":1,"order_type":"market"},
            timeout=1,
        )
        auto_locked=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"auto_start","scope":"ALL"},
            timeout=1,
        )
        assert order_locked.status_code == 403
        assert auto_locked.status_code == 403

        bridge.unlock_live()

        order_ok=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"order","side":"BUY","code":"001520","qty":1,"order_type":"market"},
            timeout=1,
        )
        auto_ok=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"auto_start","scope":"ALL"},
            timeout=1,
        )
        assert order_ok.status_code == 202
        assert auto_ok.status_code == 202

        bridge.lock_live()
        stop_ok=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"auto_stop"},
            timeout=1,
        )
        assert stop_ok.status_code == 202
    finally:
        bridge.stop()


def test_state_exposes_single_live_unlock_only(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    bridge.publish({"version":"2.8.2"})
    state=bridge.state()
    assert state["mobile_live_unlocked"] is False
    assert "mobile_order_enabled" not in state
    assert "mobile_auto_enabled" not in state
    bridge.unlock_live()
    bridge.publish({"version":"2.8.2"})
    assert bridge.state()["mobile_live_unlocked"] is True
