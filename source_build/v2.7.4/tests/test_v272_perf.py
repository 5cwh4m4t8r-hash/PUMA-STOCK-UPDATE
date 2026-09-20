from puma_trader import performance as p


def test_n5095a_profile_still_keeps_full_cache():
    old_cpu_name = p._cpu_name
    old_mem = p._total_memory_gb
    old_count = p.os.cpu_count
    try:
        p._cpu_name = lambda: "Intel(R) Celeron(R) N5095A @ 2.00GHz"
        p._total_memory_gb = lambda: 12.0
        p.os.cpu_count = lambda: 4
        x = p.detect_device_profile()
        assert (x.display_cache_entries, x.analysis_cache_entries, x.range_cache_entries) == (12,24,6)
        assert x.low_power and not x.very_low_power
    finally:
        p._cpu_name = old_cpu_name
        p._total_memory_gb = old_mem
        p.os.cpu_count = old_count
