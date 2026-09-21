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


def test_mobile_bridge_auth_and_single_live_lock(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    port=free_port()
    bridge.publish({
        "version":"2.8.2",
        "selected":{"code":"001520","name":"동양","chart":{"candles":[]}},
    })
    info=bridge.start(port)
    base=f"http://127.0.0.1:{info['port']}"
    headers={"X-Puma-Token":bridge.token}
    try:
        wait_ping(base)

        r=requests.get(base+"/api/state",timeout=1)
        assert r.status_code == 401

        state=requests.get(base+"/api/state",headers=headers,timeout=1).json()
        assert state["selected"]["code"] == "001520"
        assert state["mobile_live_unlocked"] is False

        denied=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"order","side":"BUY","code":"001520","qty":1,"order_type":"market"},
            timeout=1,
        )
        assert denied.status_code == 403

        unlock=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"unlock_live","phrase":"PUMA LIVE"},
            timeout=1,
        )
        assert unlock.status_code == 202
    finally:
        bridge.stop()


def test_mobile_live_unlock_persists_and_token_regen_relocks(tmp_path: Path):
    path=tmp_path/"mobile.json"
    a=MobileBridge(config_path=path)
    token=a.token
    assert a.live_unlocked is False
    a.unlock_live()
    assert a.live_unlocked is True

    b=MobileBridge(config_path=path)
    assert b.token == token
    assert b.live_unlocked is True

    new_token=b.regenerate_token()
    assert new_token != token
    assert b.live_unlocked is False

    c=MobileBridge(config_path=path)
    assert c.token == new_token
    assert c.live_unlocked is False


def test_pwa_assets_include_one_time_unlock_ui(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    port=free_port()
    bridge.start(port)
    base=f"http://127.0.0.1:{port}"
    try:
        wait_ping(base)
        html=requests.get(base+"/",timeout=1).text
        js=requests.get(base+"/app.js",timeout=1).text
        manifest=requests.get(base+"/manifest.webmanifest",timeout=1).json()
        assert "PUMA STOCK MOBILE" in html
        assert "실전 기능 최초 1회 잠금 해제" in html
        assert "unlockLive" in js
        assert "PUMA LIVE" in js
        assert "LIVE ORDER" not in js
        assert "LIVE START" not in js
        assert manifest["display"] == "standalone"
    finally:
        bridge.stop()
