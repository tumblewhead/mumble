"""Short reproducible host component profile; neither full solver nor M23 timing."""
import argparse,json,platform,time
from pathlib import Path
import numpy as np
from experiments.distinct_bank_integration_001.test_bank import BankTests
from experiments.distinct_bank_integration_001.run import MAP
from .field import SmallField,projection

def run():
 BankTests.setUpClass()
 try:
  f=BankTests();obs=f.obs[:16];results={}
  for rank in [13,3,4,5]:
   timings=[]
   for repeat in range(5):
    obj=f.make() if rank==13 else SmallField(f.reg['config'],f.center,f.bins['rc'],f.bins['h'],MAP,'fixture',Path(f.temporary.name)/'qr',rank,'float64')
    start=time.process_time()
    for i in range(256):obj.update(i*16,obs)
    timings.append(time.process_time()-start)
   results[str(rank)]=dict(cpu_s=timings,median_us_per_16_records=float(np.median(timings)*1e6/256))
  return dict(scope='Host response plus history update only; repeated16-record public fixture, no readout or full refit. Construction/build excluded; no MCU speed claim.',machine=platform.machine(),python=platform.python_version(),numpy=np.__version__,results=results)
 finally:BankTests.tearDownClass()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.exists():raise FileExistsError(a.out)
 a.out.write_text(json.dumps(run(),indent=2)+'\n')
