from puma_trader import performance as p


def test_n5095a_12gb_keeps_cache_and_reduces_cpu_contention(monkeypatch):
    monkeypatch.setattr(p, "_cpu_name", lambda: "Intel(R) Celeron(R) N5095A @ 2.00GHz")
    monkeypatch.setattr(p, "_total_memory_gb", lambda: 12.0)
    monkeypatch.setattr(p.os, "cpu_count", lambda: 4)
    x = p.detect_device_profile()
    assert x.low_power is True
    assert x.very_low_power is False
    assert (x.display_cache_entries, x.analysis_cache_entries, x.range_cache_entries) == (12, 24, 6)
    assert x.background_delay_ms == 900
    assert x.antialias_bar_limit == 90
