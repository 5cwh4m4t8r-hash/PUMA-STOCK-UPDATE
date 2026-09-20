import sys,os,time,json
from pathlib import Path
from datetime import datetime,timedelta
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,sys.argv[1])
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, QEvent
from puma_trader.ui import MainWindow
from puma_trader.swing_chart import SwingChart

def rows(n,minute=False):
 out=[];p=100.
 for i in range(n):
  p+=.12 if i%10<5 else -.10
  dt=datetime(2020,1,1)+ (timedelta(minutes=i*5) if minute else timedelta(days=i))
  out.append(dict(date=dt.strftime('%Y%m%d%H%M%S' if minute else '%Y%m%d'),open=p-.15,high=p+1.2,low=p-1.2,close=p,volume=4200 if i>30 and i%37==0 else 1000))
 return out
class Broker:
 name='BENCH';is_live=False
 def __init__(self):self.daily=rows(2400);self.minute=rows(1200,True)
 def iter_chart_pages(self,code,kind,max_pages,**kw):
  data=self.daily if kind=='daily' else self.minute
  size=600 if kind=='daily' else 300
  for page in range(1,5):
   time.sleep(.05)
   yield data[-page*size:], page==4
 def get_minute_candles(self,code,timeframe,max_pages=1):
  for r,_ in self.iter_chart_pages(code,'minute',4):pass
  return r
 def get_daily_candles(self,code,max_pages=8):
  for r,_ in self.iter_chart_pages(code,'daily',8):pass
  return r
app=QApplication([]);w=MainWindow();w.broker=Broker();w.show()
app.processEvents()
records={};start=time.perf_counter()
class PaintObserver(QObject):
 def eventFilter(self,obj,event):
  if event.type()==QEvent.Paint and obj.series and obj.series.get('candles'):
   records.setdefault('chart_painted_ms',round((time.perf_counter()-start)*1000,2))
  return False
observer=PaintObserver();w.focus_chart.installEventFilter(observer)

def wait_done():
 limit=time.monotonic()+30
 while time.monotonic()<limit:
  app.processEvents()
  if w.focus_daily_analysis is not None:
   records.setdefault('first_analysis_ms',round((time.perf_counter()-start)*1000,2))
  readers = getattr(w,'_focus_readers',None)
  loading=bool(readers) if readers is not None else w.focus_load_thread is not None
  analyzing=w.focus_analysis_thread is not None or w.focus_analysis_pending is not None
  if not loading and not analyzing and w.focus_daily_analysis is not None:
   app.processEvents();return
  time.sleep(.002)
 raise RuntimeError('benchmark timeout')
w.open_focus_stock('005930','BENCH');wait_done();records['full_complete_ms']=round((time.perf_counter()-start)*1000,2)
cold=dict(records);records={};start=time.perf_counter()
w.open_focus_stock('005930','BENCH');wait_done();records['full_complete_ms']=round((time.perf_counter()-start)*1000,2)
report={'cold':cold,'warm':dict(records),'daily_bars':2400,'minute_bars':1200,'simulated_page_ms':50}
print(json.dumps(report));Path(sys.argv[2]).write_text(json.dumps(report,indent=2))
w.close();app.processEvents()
