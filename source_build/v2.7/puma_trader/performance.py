"""Bounded display caches and cooperative analysis cancellation.

These caches are for charts only. Order/position logic never reads them.
"""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    """Runtime tuning only; trading/analysis thresholds are never changed."""
    cpu_count: int
    memory_gb: float
    low_power: bool
    very_low_power: bool
    display_cache_entries: int
    analysis_cache_entries: int
    range_cache_entries: int
    background_delay_ms: int
    antialias_bar_limit: int


def _total_memory_gb() -> float:
    try:
        if os.name == "nt":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            state = MEMORYSTATUSEX()
            state.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                return round(state.ullTotalPhys / (1024 ** 3), 2)
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round((pages * page_size) / (1024 ** 3), 2)
    except Exception:
        pass
    return 0.0


def detect_device_profile() -> DeviceProfile:
    cpu = max(1, int(os.cpu_count() or 1))
    mem = _total_memory_gb()
    forced = str(os.environ.get("PUMA_PERFORMANCE_MODE") or "").strip().lower()
    if forced in {"very_low", "ultra", "legacy"}:
        return DeviceProfile(cpu, mem, True, True, 4, 8, 3, 1000, 80)
    if forced in {"low", "laptop", "eco"}:
        return DeviceProfile(cpu, mem, True, False, 6, 12, 4, 650, 110)
    if forced in {"normal", "desktop", "full"}:
        return DeviceProfile(cpu, mem, False, False, 12, 24, 6, 80, 220)

    very_low = bool((mem and mem <= 4.75 and cpu <= 4) or cpu <= 2)
    low = bool(very_low or (mem and mem <= 8.25 and cpu <= 4))
    if very_low:
        return DeviceProfile(cpu, mem, True, True, 4, 8, 3, 1000, 80)
    if low:
        return DeviceProfile(cpu, mem, True, False, 6, 12, 4, 650, 110)
    return DeviceProfile(cpu, mem, False, False, 12, 24, 6, 80, 220)


DEVICE_PROFILE = detect_device_profile()


class AnalysisCancelled(Exception):
    pass


_cancelled = ContextVar('puma_analysis_cancelled', default=lambda: False)


def check_cancelled():
    if _cancelled.get()():
        raise AnalysisCancelled()


@contextmanager
def analysis_scope(cancelled):
    token = _cancelled.set(cancelled)
    try:
        check_cancelled()
        yield
    finally:
        _cancelled.reset(token)


def settings_key(value):
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def data_revision(minute, daily):
    # All bars and fields participate; corrections to old bars invalidate results.
    raw = json.dumps([minute, daily], sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.blake2b(raw.encode(), digest_size=16).hexdigest()


class DisplayCache:
    """GUI-thread-owned LRU; entries retain their source timestamps."""
    def __init__(self, max_entries=12):
        self.max_entries = max_entries
        self._items = OrderedDict()

    def get(self, key, default=None):
        if key not in self._items:
            return default
        self._items.move_to_end(key)
        return self._items[key]

    def put(self, key, value):
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def clear(self):
        self._items.clear()


class ChartRequestGate:
    """Share a conservative chart/info request budget across read workers."""
    def __init__(self, interval=0.25):
        self.interval = interval
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self, cancelled=lambda: False):
        while True:
            if cancelled():
                raise AnalysisCancelled()
            with self._lock:
                delay = self._next - time.monotonic()
                if delay <= 0:
                    self._next = time.monotonic() + self.interval
                    return
            time.sleep(min(delay, 0.025))
