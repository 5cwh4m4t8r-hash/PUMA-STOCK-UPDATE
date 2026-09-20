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


def test_mobile_bridge_auth_state_and_order_lock(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    port=free_port()
    bridge.publish({
        "version":"2.8.0",
        "selected":{"code":"001520","name":"동양","chart":{"candles":[]}},
    })
    info=bridge.start(port)
    base=f"http://127.0.0.1:{info['port']}"
    try:
        for _ in range(30):
            try:
                if requests.get(base+"/api/ping",timeout=.3).ok:
                    break
            except Exception:
                time.sleep(.03)

        r=requests.get(base+"/api/state",timeout=1)
        assert r.status_code == 401

        headers={"X-Puma-Token":bridge.token}
        r=requests.get(base+"/api/state",headers=headers,timeout=1)
        assert r.status_code == 200
        assert r.json()["selected"]["code"] == "001520"

        r=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"order","side":"BUY","code":"001520","qty":1,"order_type":"market"},
            timeout=1,
        )
        assert r.status_code == 403

        r=requests.post(
            base+"/api/command",
            headers=headers,
            json={"type":"select_stock","code":"001520","name":"동양"},
            timeout=1,
        )
        assert r.status_code == 202
        rid=r.json()["request_id"]
        status=requests.get(base+"/api/command/"+rid,headers=headers,timeout=1).json()
        assert status["status"] == "pending"
    finally:
        bridge.stop()


def test_mobile_bridge_token_persists(tmp_path: Path):
    path=tmp_path/"mobile.json"
    a=MobileBridge(config_path=path)
    token=a.token
    b=MobileBridge(config_path=path)
    assert b.token == token
    assert len(token) == 6 and token.isdigit()


def test_pwa_assets_are_served(tmp_path: Path):
    bridge=MobileBridge(config_path=tmp_path/"mobile.json")
    port=free_port()
    bridge.start(port)
    base=f"http://127.0.0.1:{port}"
    try:
        html=requests.get(base+"/",timeout=1).text
        assert "PUMA STOCK MOBILE" in html
        manifest=requests.get(base+"/manifest.webmanifest",timeout=1).json()
        assert manifest["display"] == "standalone"
        js=requests.get(base+"/app.js",timeout=1).text
        assert "submitOrder" in js
        assert "setChartMode" in js
    finally:
        bridge.stop()
