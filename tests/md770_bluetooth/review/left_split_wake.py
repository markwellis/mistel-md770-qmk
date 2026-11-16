from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from stock_trace import Trace
from stock_probe import Stock
from unicorn import UC_HOOK_MEM_WRITE
b=Path('mistel_md770rgb_bt_left_stock.bin').read_bytes()
def new():
 s=Trace.__new__(Trace);Stock.__init__(s,b);s.leds=[];s.mmio=[];s.cpu.hook_add(UC_HOOK_MEM_WRITE,s.store,begin=0x40000000,end=0x400fffff)
 s.put(0x400b2004,0x100,4);s.put(0x400b200c,0x100,4)
 return s
for old,newlevel in ((13,4),(4,13)):
 s=new();s.put(0x20000354,newlevel);s.put(0x20000355,old);s.call(0x4ba8,0)
 if newlevel==4:s.call(0x879c,0)
 print(json.dumps({'old':old,'new':newlevel,'wake_enable':hex(s.get(0x40024050,4)),'AFIO_ESSR1':hex(s.get(0x40022004,4)),'GPIOB_inputenable':hex(s.get(0x400b2004,4)),'GPIOB_pulldown':hex(s.get(0x400b200c,4)),'B8_event_return':s.call(0x4cf0,0x100),'matrix_event_return':s.call(0x4cf0,0xff),'writes':s.mmio}))
