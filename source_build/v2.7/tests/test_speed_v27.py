"""Behavioral regressions for progressive reads, cache validity and latest-click wins."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from datetime import datetime, timedelta
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from puma_trader.ui import MainWindow
from puma_trader.chart_loader import FocusDataThread
from puma_trader.performance import DisplayCache, data_revision, AnalysisCancelled


def rows(n=520, minute=False, offset=0):
    start = datetime(2020, 1, 1)
    out = []
    for i in range(n):
        price = 100 + offset + i * .01 + (i % 9) * .15
        date = start + timedelta(minutes=i*5) if minute else start + timedelta(days=i)
        out.append(dict(date=date.strftime('%Y%m%d%H%M%S' if minute else '%Y%m%d'),
                        open=price-.1, high=price+1, low=price-1, close=price,
                        volume=4200 if i % 37 == 0 else 1000))
    return out


class FakeBroker:
    name = 'TEST'
    is_live = False
    def __init__(self, delay=.01, tail=.10):
        self.delay, self.tail = delay, tail
        self.calls = []
    def iter_chart_pages(self, code, kind, max_pages, **kwargs):
        self.calls.append((code, kind))
        data = rows(620 if kind == 'daily' else 260, kind == 'minute', int(code[-1]))
        time.sleep(self.delay)
        yield data[-520:], False
        deadline = time.monotonic() + self.tail
        while time.monotonic() < deadline:
            if kwargs['cancelled']():
                raise AnalysisCancelled()
            time.sleep(.002)
        yield data, True
    def get_stock_info(self, code):
        return {'stk_nm': 'T' + code, 'cur_prc': '109'}


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def pump(app, predicate, timeout=8):
    end = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() > end:
            raise AssertionError('GUI worker did not finish')
        time.sleep(.002)
    app.processEvents()


@pytest.fixture
def window(app):
    w = MainWindow()
    w.broker = FakeBroker()
    yield w
    w.close()
    pump(app, lambda: not w._focus_readers and w.focus_analysis_thread is None and w.danta_analysis_thread is None)
    w.close()
    app.processEvents()


def idle(w):
    return not w._focus_readers and w.focus_analysis_thread is None and not w.focus_analysis_pending


def test_preview_is_delivered_before_history_is_finished(app, window):
    w=window;w.broker=FakeBroker(tail=.45)
    w.open_focus_stock('000001')
    pump(app, lambda: bool(w.focus_chart.series and w.focus_chart.series.get('candles')))
    assert w._focus_readers, 'Chart must appear while history is still being fetched'
    assert w.focus_latency_ms['chart'] < 350
    pump(app, lambda: idle(w))
    assert len(w.focus_daily_raw) == 620  # history was retained


def test_completed_results_reopen_without_network_or_cpu(app, window, monkeypatch):
    w=window;w.open_focus_stock('000001');pump(app, lambda: idle(w))
    w.open_focus_stock('000002');pump(app, lambda: idle(w))
    calls=len(w.broker.calls)
    import puma_trader.ui as ui
    def fail(*a, **kw):
        raise AssertionError('Cached click must not recompute analysis')
    monkeypatch.setattr(ui, 'analyze_swing', fail)
    w.open_focus_stock('000001')
    assert w.focus_daily_analysis is not None
    assert w.focus_data_code == '000001'
    assert len(w.broker.calls) == calls
    assert w.focus_analysis_thread is None
    assert w.focus_latency_ms['complete'] < 150


def test_latest_click_wins_and_old_errors_do_not_overwrite(app, window):
    w=window;w.broker=FakeBroker(tail=.18)
    for code in ('000001','000002','000003','000001','000003'):
        w.open_focus_stock(code)
        app.processEvents()
    assert len(w._focus_readers) <= 2
    pump(app, lambda: idle(w) and not w._focus_fetch_pending)
    assert w.selected_code == w.focus_data_code == '000003'
    assert w.focus_daily_analysis.current_price == pytest.approx(rows(620,offset=3)[-1]['close'])
    assert '000003' in w.focus_title.text()


def test_changed_settings_do_not_reuse_completed_view(app, window):
    w=window;w.open_focus_stock('000001');pump(app, lambda: idle(w))
    old=w._focus_view_key()
    w.focus_tp.setValue(w.focus_tp.value()+1)
    assert w._focus_view_key() != old
    assert w._display_cache.get(w._focus_view_key()) is None
    broker=w.broker
    w.broker=FakeBroker()
    assert w._display_cache.get(w._focus_view_key()) is None
    w.broker=broker


def test_raw_revision_detects_old_bar_corrections():
    x=rows(520);first=data_revision([],x)
    x[3]['close']+=.001
    assert data_revision([],x)!=first


def test_cache_is_bounded_and_promotes_recent_reads():
    c=DisplayCache(2);c.put('a',1);c.put('b',2)
    assert c.get('a')==1
    c.put('c',3)
    assert c.get('b') is None
    assert c.get('a')==1


def test_quote_error_keeps_chart_data(app, window):
    w=window
    class BrokenQuote(FakeBroker):
        def get_stock_info(self, code):
            raise RuntimeError('quote unavailable')
    w.broker=BrokenQuote()
    w.open_focus_stock('000001');pump(app,lambda: idle(w))
    assert w.focus_daily_analysis is not None
    assert '시세' in w.focus_origin.text()


def test_close_interrupts_outstanding_reads_without_destroying_thread(app, window):
    w=window;w.broker=FakeBroker(tail=2)
    w.open_focus_stock('000001')
    pump(app,lambda: bool(w._preview_series))
    w.close()
    pump(app,lambda: idle(w), timeout=2)
    assert w._closing


def test_condition_classification_prepares_click_result(app, window):
    from puma_trader.ui import CandidateClassifier
    w=window
    class PrefetchBroker(FakeBroker):
        def get_minute_candles(self, code, timeframe):
            return rows(260, True)
        def get_daily_candles(self, code, max_pages):
            return rows(620)
    w.broker=PrefetchBroker()
    worker=CandidateClassifier(w.broker,'000001','08:50','10:00',w._swing_settings_from_ui(),w.bowl_settings)
    worker.context_key=w._focus_view_key('000001')
    found=[];worker.resultReady.connect(lambda code, result: found.append(result))
    worker.run()
    assert found[0]['prepared']['result']['swing_analysis'] is not None
    assert found[0]['name']=='T000001'
    w._on_candidate_classified('000001',found[0])
    w.open_focus_stock('000001')
    assert w.focus_daily_analysis is not None  # synchronous completed-view restore
    assert w._focus_readers  # prefetch data is explicitly provisional; refresh continues
    pump(app,lambda:idle(w))


def test_range_calculation_keeps_gui_free_and_all_view_rejects_old_result(app, window):
    w=window;w.open_focus_stock('000001');pump(app,lambda:idle(w))
    t=time.perf_counter();w._analyze_focus_range(200,500,'test range')
    assert time.perf_counter()-t < .15
    assert w._range_worker is not None
    w.focus_analyze_all()
    pump(app,lambda:w._range_worker is None)
    assert w.focus_range_status.text()=='분석: 전체'


def test_paging_deduplicates_boundaries_and_stops_on_cancel():
    from puma_trader.broker import KiwoomRestBroker
    broker=KiwoomRestBroker('test','test')
    pages=[({'stk_dt_pole_chart_qry':[{'dt':'3'},{'dt':'2'}]},'Y','next'),
           ({'stk_dt_pole_chart_qry':[{'dt':'2'},{'dt':'1'}]},'N','')]
    broker._post_page=lambda *a:pages.pop(0)
    result=list(broker.iter_chart_pages('000001','daily',8))
    assert [r['dt'] for r in result[-1][0]]==['3','2','1']
    assert result[-1][1]
    with pytest.raises(AnalysisCancelled):
        next(broker.iter_chart_pages('000001','daily',8,cancelled=lambda:True))
    broker.session.close()


def test_history_prepend_keeps_latest_or_the_selected_historical_date(app):
    from puma_trader.swing_chart import SwingChart
    chart=SwingChart();all_rows=rows(1000)
    chart.set_basic_data(all_rows[-520:])
    chart.set_basic_data(all_rows,preserve_view=True)
    assert chart.view_end==1000
    chart.set_basic_data(all_rows[-520:])
    chart.pan_bars(-100)
    anchor=chart.series['candles'][chart.view_end-1]['date']
    chart.set_analysis_range(200,300)
    chosen=chart.series['candles'][200]['date']
    chart.set_basic_data(all_rows,preserve_view=True)
    assert chart.series['candles'][chart.view_end-1]['date']==anchor
    assert chart.series['candles'][chart.analysis_range[0]]['date']==chosen
    chart.close()


def test_refresh_keeps_cached_history_until_full_replacement(app, window):
    w=window;w.open_focus_stock('000001');pump(app,lambda:idle(w))
    old_series=w.focus_daily_series
    w.broker.tail=.35
    w.focus_refresh(force=True)
    pump(app,lambda:bool(w._preview_series))
    # Explicitly deliver a short first-page response in the current generation.
    w._focus_load_ready(dict(code='000001',request_id=w._focus_request_id,complete=False,
        daily=rows(520),minute=rows(200,True),info={},loaded_at=time.time(),revision='short'))
    assert w.focus_daily_series is old_series
    assert len(w.focus_daily_raw)==620
    pump(app,lambda:idle(w))
