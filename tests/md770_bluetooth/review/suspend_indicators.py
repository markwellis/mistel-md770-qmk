import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk,Stock
from unicorn import UC_HOOK_CODE
qhome=Path('../qmk_firmware').resolve();elf=qhome/'.build/mistel_md770rgb_bt_right_default_conformance.elf';image=elf.read_bytes();abi=layout(qhome,elf)
q=Qmk(image,abi);s=Stock(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes())
q.hardware.pin(1,12,True);q.hardware.pin(0,10,False);q.write(q.symbol('supply'),3,1);q.write(q.symbol('eligible'),1,1);q.set_host('host_usb');q.write(q.symbol('active_host'),abi['host_usb'],1);q.usb(True);q.write(q.symbol('caps'),1,1);q.indicators()
s.ready();s.hardware.registers[0x40088040]=0
for pad in (2,3,4,5):s.hardware.pin(1,pad,pad==2)
s.hardware.pin(1,12,True);s.hardware.pin(0,10,False)
for a,v in [(0x2000001f,4),(0x20000020,1),(0x20000601,5),(0x20000603,4),(0x20000623,13),(0x20000624,13),(0x20000625,13),(0x20000626,0x10),(0x200001e4,2),(0x20000219,4),(0x20000218,0x20),(0x2000068c,1),(0x2000068a,2)]:s.write(a,v,1)
s.write(0x20000628,0);s.indicators()
result={'elf_sha256':hashlib.sha256(image).hexdigest(),'before':{'qmk_red':q.hardware.registers[0x4006e098],'stock_red':s.hardware.registers[0x4006e098]}}
regs={a:0 for a in (0x400a8000,0x400a8004,0x400a8008,0x400a8010,0x400a8028,0x400a803c)}
access=s.hardware.access
def extra(address,size,value=None):
 if address in regs:
  if value is None:return regs[address]
  if address==0x400a8008:regs[address]&=~value
  else:regs[address]=value
  return 0
 return access(address,size,value)
s.hardware.access=extra
regs[0x400a8004]=regs[0x400a8008]=0x10;s.call(0x989c)
trace=[]
s.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,z,c:trace.append(hex(a)) if a in (0x9a44,0xd7e4,0x6d04,0x88e8,0xc87c,0x84fc) else None)
s.call(0xda78,budget=1000000);s.indicators()
q.usb(True,suspended=True);q.call('md770_power_task');q.indicators()
result['after']={'qmk_red':q.hardware.registers[0x4006e098],'stock_red':s.hardware.registers[0x4006e098],'qmk_rgb_asleep':q.read(q.symbol('asleep'),1),'stock_power':s.read(0x20000624,1),'stock_usb_state':s.read(0x20000601,1),'stock_charge':s.read(0x20000020,1),'trace':trace}
print(json.dumps(result,indent=2))
