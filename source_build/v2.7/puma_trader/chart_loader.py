"""Progressive, cancellable chart reads with isolated HTTP sessions."""
import time
from PySide6.QtCore import QThread, Signal
from .broker import KiwoomRestBroker
from .performance import AnalysisCancelled, data_revision
from .swing import normalize_candles


def reader_broker(broker, cancelled=lambda: False):
    if not isinstance(broker, KiwoomRestBroker):
        return broker
    reader = KiwoomRestBroker(broker.app_key, broker.app_secret,
                             real=broker.real, order_exchange=broker.order_exchange)
    reader.token = broker.token
    reader.token_expire_epoch = broker.token_expire_epoch
    reader._chart_gate = broker._chart_gate
    reader._chart_cancelled = cancelled
    return reader


class FocusDataThread(QThread):
    preview = Signal(object)
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, broker, code, daily_pages, parent=None, *, mode='DAY', request_id=0):
        super().__init__(parent)
        self.broker, self.code = broker, str(code)
        self.daily_pages, self.mode = int(daily_pages), mode
        self.request_id = request_id

    def _pages(self, broker, kind):
        if hasattr(broker, 'iter_chart_pages'):
            yield from broker.iter_chart_pages(self.code, kind,
                self.daily_pages if kind == 'daily' else 4,
                cancelled=self.isInterruptionRequested)
        elif kind == 'minute':
            yield broker.get_minute_candles(self.code, 5, max_pages=4) or [], True
        else:
            getter = getattr(broker, 'get_daily_candles', None)
            yield (getter(self.code, max_pages=self.daily_pages) if getter else []), True

    def run(self):
        broker = reader_broker(self.broker, self.isInterruptionRequested)
        payload = dict(code=self.code, info={}, minute=[], daily=[], daily_pages=self.daily_pages,
                       request_id=self.request_id, errors=[], complete=False)
        done = {}
        order = ['minute', 'daily'] if self.mode == 'MIN' else ['daily', 'minute']
        streams = {kind: iter(self._pages(broker, kind)) for kind in order}

        def receive(kind):
            if self.isInterruptionRequested():
                raise AnalysisCancelled()
            try:
                rows, complete = next(streams[kind])
                payload[kind] = rows
                done[kind] = complete
                payload[kind + '_at'] = time.time()
            except StopIteration:
                done[kind] = True
            except AnalysisCancelled:
                raise
            except Exception as exc:
                payload['errors'].append(f'{kind}: {exc}')
                done[kind] = True

        def snapshot(complete):
            return {**payload, 'errors': list(payload['errors']), 'complete': complete,
                    'loaded_at': time.time(), 'revision': data_revision(payload['minute'], payload['daily'])}

        try:
            # The visible timeframe reaches the GUI after ONE response.
            for kind in order:
                receive(kind)
                self.preview.emit({**snapshot(False), 'preview_kind': kind,
                                   'preview_candles': normalize_candles(payload[kind])})
            if not self.isInterruptionRequested() and hasattr(broker, 'get_stock_info'):
                try:
                    payload['info'] = broker.get_stock_info(self.code) or {}
                    payload['quote_at'] = time.time()
                except AnalysisCancelled:
                    raise
                except Exception as exc:
                    payload['errors'].append(f'시세: {exc}')
            if self.isInterruptionRequested():
                return
            complete = all(done.values())
            self.loaded.emit(snapshot(complete))
            if not complete:
                # History stays available; it is no longer a barrier to first paint.
                for kind in order:
                    while not done[kind]:
                        receive(kind)
                if not self.isInterruptionRequested():
                    self.loaded.emit(snapshot(True))
        except AnalysisCancelled:
            pass
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
        finally:
            if broker is not self.broker:
                broker.session.close()


class NameLookupThread(QThread):
    resolved = Signal(str, str)

    def __init__(self, broker, code, parent=None):
        super().__init__(parent)
        self.broker, self.code = broker, code

    def run(self):
        broker = reader_broker(self.broker, self.isInterruptionRequested)
        try:
            info = broker.get_stock_info(self.code)
            if not self.isInterruptionRequested():
                self.resolved.emit(self.code, str(info.get('stk_nm') or info.get('name') or '').strip())
        except Exception:
            pass
        finally:
            if broker is not self.broker:
                broker.session.close()
