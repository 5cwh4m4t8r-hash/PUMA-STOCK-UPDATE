from pathlib import Path

import pytest

from puma_trader.mobile_bridge import MobileBridge
from puma_trader.remote_relay import RemoteRelayClient


def test_remote_relay_identity_and_https_validation(tmp_path):
    bridge = MobileBridge(config_path=tmp_path / "mobile.json")
    client = RemoteRelayClient(
        bridge,
        config_path=tmp_path / "mobile_remote.json",
    )
    assert len(client.device_id) == 12
    assert all(ch in "0123456789abcdef" for ch in client.device_id)
    assert len(client.pc_secret) >= 32

    with pytest.raises(ValueError):
        client.configure("http://example.com")

    client.configure("https://relay.example.com/")
    assert client.relay_url == "https://relay.example.com"


def test_remote_relay_uses_existing_mobile_command_path():
    src = Path("puma_trader/remote_relay.py").read_text(encoding="utf-8")
    assert "self.bridge.queue_command(payload)" in src
    assert "self.bridge.command_status(local_id)" in src
    assert "_LIVE_COMMANDS = {\"order\", \"auto_start\"}" in src
    assert "중복 실행을 차단했습니다" in src


def test_pc_ui_has_external_relay_controls():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert "RemoteRelayClient" in src
    assert "외부망 · PUMA iPhone 앱" in src
    assert "self.mobile_remote.start(relay_url)" in src
    assert "self.mobile_remote.stop()" in src


def test_public_relay_server_compiles_and_has_auth_rate_limit():
    root = Path(__file__).resolve().parents[3]
    relay = root / "relay" / "puma_relay_server.py"
    source = relay.read_text(encoding="utf-8")
    compile(source, str(relay), "exec")
    assert "X-Puma-PC-Secret" in source
    assert "X-Puma-Token" in source
    assert "TOO_MANY_REQUESTS" in source
    assert "ALLOWED_COMMANDS" in source


def test_native_ios_project_and_tailscale_mode_exist():
    root = Path(__file__).resolve().parents[3]
    ios = root / "ios" / "PUMAMobile"
    assert (ios / "project.yml").exists()
    client = (ios / "PUMAMobile" / "PumaClient.swift").read_text(encoding="utf-8")
    views = (ios / "PUMAMobile" / "Views.swift").read_text(encoding="utf-8")
    assert 'case direct = "Direct / Tailscale"' in client
    assert "/v1/mobile/state" in client
    assert "/api/state" in client
    assert "수동 주문" in views
    assert "자동매매" in views
