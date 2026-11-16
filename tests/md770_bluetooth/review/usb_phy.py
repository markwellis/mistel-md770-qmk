from pathlib import Path
p=Path(__file__).with_name('usb_queue.py')
source=p.read_text(); exec(source[:source.index("result={'elf_sha256'")])
from stock_trace import Trace
s=Trace(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes())
csr=0x400a8000;hsicr=0x40088040
s.put(csr,0x400,4);s.put(hsicr,0x12340023,4)
s.put(0x20000601,5);s.put(0x20000602,5);s.put(0x20000603,4)
s.put(0x20000624,13);s.put(0x20000604,2);s.put(0x200005b6,1)
access=q.hardware.access; regs={csr:0x400}
q.hardware.registers[hsicr]=0x12340023
def supplied_register(address,size,value=None):
 if address in regs:
  if value is None:return regs[address]
  regs[address]=value;return 0
 return access(address,size,value)
q.hardware.access=supplied_register
q.hardware.pin(1,12,True);q.hardware.pin(0,10,False)
q.set_host('host_usb');q.write(q.symbol('active_host'),abi['host_usb'],1);q.write(q.symbol('supply'),3,1)
def stock_irq(flag):
 s.put(csr+4,0x111f,4);s.put(csr+8,flag,4);s.call(0x989c)
def view():
 return {'stock_CSR':hex(s.get(csr,4)),'qmk_CSR':hex(regs[csr]),'stock_HSICR':hex(s.get(hsicr,4)),'qmk_HSICR':hex(q.hardware.registers[hsicr])}
result={'elf_sha256':hashlib.sha256(image).hexdigest(),'boundary':'Actual stock USB IRQ and compiled QMK USB callback/power task; USB CSR is supplied storage, not a model of PHY signalling.'}
stock_irq(0x10);q.usb(True,suspended=True,remote_wakeup=True);q.call(event,u,a['suspend']);result['suspend']=view()
s.call(0x9a44);q.write(q.symbol('usb_pending'),1,1);q.call('md770_power_task');result['remote_wake_request']=view()
stock_irq(8);regs[csr]&=~0x20;q.usb(True);q.call(event,u,a['wakeup']);result['resume']=view()
stock_irq(4);q.usb(False);q.call(event,u,a['reset']);result['reset']=view()
print(json.dumps(result,indent=2))
