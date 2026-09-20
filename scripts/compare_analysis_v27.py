import sys,json,random,time
from pathlib import Path
from datetime import datetime,timedelta
from dataclasses import asdict
sys.path.insert(0,sys.argv[1])
from puma_trader.swing import analyze,SwingSettings
from puma_trader.market_path import clear_market_path_cache
from puma_trader.bowl import analyze_bowl
from puma_trader.signals import build_arrow_signals
out=[];times=[]
for seed in range(4):
 rng=random.Random(seed); p=100.;rows=[]
 for i in range(1200):
  p=max(20,p+rng.uniform(-.8,.8)+(0.14 if seed==1 else -.05 if seed==2 else 0))
  v=1000+rng.randint(-200,200)
  if i%31==0:v*=4
  rows.append(dict(date=(datetime(2020,1,1)+timedelta(days=i)).strftime('%Y%m%d'),open=p+rng.uniform(-.6,.6),high=p+1,low=p-1,close=p,volume=v))
 clear_market_path_cache();t=time.perf_counter();a,s=analyze(rows,SwingSettings());b,bs=analyze_bowl(rows);times.append(time.perf_counter()-t)
 out.append(dict(swing=asdict(a),bowl=asdict(b),series=s))
Path(sys.argv[2]).write_text(json.dumps(dict(results=out,seconds=times)))
print(sys.argv[1], times)
