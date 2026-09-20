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


def test_mobile_auto_start_is_pc_gated_but_stop_is_always_available(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    port=free_port()
    bridge.publish({
        "version":"2.8.1",
        "auto":{"enabled":False,"scope":"ALL","settings":{}},
        "selected":{"code":"001520","name":"동양","chart":{"candles":[]}},
    })
    bridge.start(port)
    base=f"http://127.0.0.1:{port}"
    headers={"X-Puma-Token":bridge.token}
    try:
        wait_ping(base)

        denied=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"auto_start","scope":"ALL"},
            timeout=1,
        )
        assert denied.status_code == 403

        bridge.set_auto_enabled(True)
        accepted=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"auto_start","scope":"ALL"},
            timeout=1,
        )
        assert accepted.status_code == 202
        rid=accepted.json()["request_id"]
        status=requests.get(base+"/api/command/"+rid,headers=headers,timeout=1).json()
        assert status["status"] == "pending"

        bridge.set_auto_enabled(False)
        stop=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"auto_stop"},
            timeout=1,
        )
        assert stop.status_code == 202
    finally:
        bridge.stop()


def test_state_exposes_mobile_auto_permission(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    bridge.publish({"version":"2.8.1"})
    assert bridge.state()["mobile_auto_enabled"] is False
    bridge.set_auto_enabled(True)
    bridge.publish({"version":"2.8.1"})
    assert bridge.state()["mobile_auto_enabled"] is True
