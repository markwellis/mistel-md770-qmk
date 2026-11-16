import json,sys,hashlib
from pathlib import Path
sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_firmware import Qmk
from emulator_abi import layout
from stock_trace import Trace
elf=Path('../qmk_firmware/.build/mistel_md770rgb_bt_right_default_conformance_validation.elf').resolve()
q=Qmk(elf.read_bytes(),layout(elf.parent.parent,elf))
s=Trace(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes())
csr=0x400a8000
s.put(0x20000603,4);s.put(0x20000601,0);s.put(0x20000602,5);s.put(0x20000604,2);s.put(0x20000624,13);s.put(0x200005b6,1)
s.put(csr,0x40c,4)
access=q.hardware.access;regs={csr:0x40c};writes=[]
def supplied(address,size,value=None):
 if address==csr:
  if value is None:return regs[address]
  regs[address]=value;writes.append(value);return 0
 return access(address,size,value)
q.hardware.access=supplied
q.hardware.pin(1,12,True);q.hardware.pin(0,10,False)
q.set_host('host_usb');q.write(q.symbol('active_host'),q.abi['host_usb'],1)
q.write(q.symbol('supply'),3,1);q.write(q.symbol('external'),1,1);q.write(q.symbol('usb_pending'),1,1)
q.usb(True,suspended=True,remote_wakeup=True)
rows=[]
for now in (0,1,99,100):
 q.ms=now;s.mmio.clear();writes.clear()
 s.call(0x9a44);q.call('md770_power_task')
 rows.append({'ms':now,'stock_csr_writes':[x[2] for x in s.mmio if x[0]=='0x400a8000'],'qmk_csr_writes':list(writes),'stock_dirty':s.get(0x200005b6),'qmk_pending':q.read(q.symbol('usb_pending'),1)})
print(json.dumps({'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'boundary':'Actual stock 9a44 and compiled power task with supplied CSR storage, pending keyboard and suspended USB state; no physical wake signalling model.','observations':rows},indent=2))
