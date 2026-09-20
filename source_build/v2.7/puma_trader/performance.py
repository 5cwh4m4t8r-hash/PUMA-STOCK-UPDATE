"""Bounded display caches and cooperative analysis cancellation.

These caches are for charts only. Order/position logic never reads them.
"""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
import hashlib
import json
import threading
import time


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
