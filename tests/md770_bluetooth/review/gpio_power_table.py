from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from stock_trace import Trace
from stock_probe import Stock
from unicorn import UC_HOOK_MEM_WRITE
for side,callback,power,table,count in [('right',0x52cc,0x20000620,0xe631,9),('left',0x4ba8,0x20000350,0xb0f5,5)]:
 b=Path('mistel_md770rgb_bt_'+side+'_stock.bin').read_bytes();s=Trace.__new__(Trace);Stock.__init__(s,b);s.mmio=[];s.leds=[]
 def track(cpu,access,address,size,value,unused):
  s.store(cpu,access,address,size,value,unused)
  if 0x400b0000<=address<0x400b8000 and address%0x2000 in (0x24,0x28):
   base=address-(address%0x2000);out=s.get(base+0x20,4)
   if address-base==0x24:out=(out|(value&0xffff))&~(value>>16)
   else:out&=~value
   s.put(base+0x20,out,4)
 s.cpu.hook_add(UC_HOOK_MEM_WRITE,track,begin=0x40000000,end=0x400fffff)
 pins=[b[a-0x3200:a-0x3200+6] for a in range(table,table+count*6,6)]
 def state():
  out=[]
  for record in pins:
   port,pad=record[:2];base=0x400b0000+port*0x2000;bit=1<<pad
   row={'pin':chr(65+port)+str(pad),'table':record.hex(' '),'af':(s.get(0x40022020+port*8+(pad//8)*4,4)>>(pad%8*4))&15}
   for name,offset in [('output',0),('input',4),('pull_up',8),('pull_down',12),('open_drain',16),('drive',20),('level',32)]:row[name]=bool(s.get(base+offset,4)&bit)
   out.append(row)
  return out
 records=[]
 for old,new in [(0,13),(13,4),(4,13)]:
  s.put(power+4,new);s.put(power+5,old);s.mmio=[];s.call(callback,0)
  records.append({'old':old,'new':new,'pins':state(),'wake_enable':hex(s.get(0x40024050,4)),'writes':s.mmio})
 print(json.dumps({'side':side,'sha256':hashlib.sha256(b).hexdigest(),'transitions':records}))
