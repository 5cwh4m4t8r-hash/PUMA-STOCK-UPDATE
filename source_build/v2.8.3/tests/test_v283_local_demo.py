import socket
import time
from pathlib import Path

import requests

from puma_trader.mobile_bridge import MobileBridge


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_ping(base):
    for _ in range(50):
        try:
            if requests.get(base + "/api/ping", timeout=.3).ok:
                return
        except Exception:
            time.sleep(.03)
    raise AssertionError("mobile bridge did not start")


def test_local_interactive_demo_served_without_external_host(tmp_path: Path):
    bridge = MobileBridge(config_path=tmp_path / "mobile.json")
    port = free_port()
    bridge.start(port)
    base = f"http://127.0.0.1:{port}"
    try:
        wait_ping(base)
        r = requests.get(base + "/demo", timeout=1)
        assert r.status_code == 200
        html = r.text
        assert "PUMA STOCK MOBILE" in html
        assert "작동형 DEMO" in html
        assert "자동매매 시작" in html
        assert "PUMA LIVE" in html
        assert "onclick=\"go('settings',this)\"" in html
        assert "setInterval(tick,1800)" in html
        assert "자동매수" in html
        assert "자동매도" in html
    finally:
        bridge.stop()


def test_local_demo_needs_no_pairing_token(tmp_path: Path):
    bridge = MobileBridge(config_path=tmp_path / "mobile.json")
    port = free_port()
    bridge.start(port)
    base = f"http://127.0.0.1:{port}"
    try:
        wait_ping(base)
        assert requests.get(base + "/demo", timeout=1).status_code == 200
        assert requests.get(base + "/api/state", timeout=1).status_code == 401
    finally:
        bridge.stop()
