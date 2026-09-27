import json

import puma_trader.updater as updater


class _Resp:
    def __init__(self, payload: bytes):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return self.payload


def test_version_compare_detects_2955_from_2952(monkeypatch):
    monkeypatch.setattr(updater, "CURRENT_VERSION", "2.9.52")
    payload = json.dumps({
        "version": "2.9.55",
        "url": "https://example.com/PUMA_STOCK_PRO_v2.9.55_UPDATE.zip",
        "sha256": "abc",
    }).encode("utf-8")

    seen = {}
    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        return _Resp(payload)

    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_urlopen)
    info = updater.fetch_manifest(updater.DEFAULT_MANIFEST_URL)

    assert info.version == "2.9.55"
    assert info.newer is True
    assert "_puma_ts=" in seen["url"]
    headers = {k.lower(): v for k, v in seen["headers"].items()}
    assert "no-cache" in headers["cache-control"].lower()
    assert "no-cache" in headers["pragma"].lower()


def test_invalid_saved_manifest_url_falls_back_to_official(tmp_path, monkeypatch):
    root = tmp_path / "app"
    cfg = root / "config" / "update.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"manifest_url":"not-a-url"}', encoding="utf-8")

    monkeypatch.setattr(updater, "app_root", lambda: root)
    loaded = updater.load_update_config()
    assert loaded["manifest_url"] == updater.DEFAULT_MANIFEST_URL


def test_blank_manifest_argument_uses_official_url(monkeypatch):
    payload = json.dumps({
        "version": "9.9.9",
        "url": "https://example.com/update.zip",
        "sha256": "abc",
    }).encode("utf-8")

    seen = {}
    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        return _Resp(payload)

    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_urlopen)
    updater.fetch_manifest("")
    assert seen["url"].startswith(updater.DEFAULT_MANIFEST_URL)
