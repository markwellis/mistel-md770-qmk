from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from stock_trace import Trace
from stock_probe import Stock
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
for side,entry,wake in [('right',0x34f0,0xab04),('left',0x33dc,0x879c)]:
 b=Path('mistel_md770rgb_bt_'+side+'_stock.bin').read_bytes()
 s=Trace.__new__(Trace)
 Stock.__init__(s,b)
 s.leds=[];s.mmio=[]
 s.cpu.hook_add(UC_HOOK_MEM_WRITE,s.store,begin=0x40000000,end=0x400fffff)
 s.call(entry)
 print(json.dumps({'side':side,'sha256':hashlib.sha256(b).hexdigest(),'watchdog_writes':s.mmio}))
 s.mmio=[];s.call(wake,0)
 print(json.dumps({'side':side,'wake_writes':s.mmio,'wake_mask':s.get(0x40024050,4)}))
