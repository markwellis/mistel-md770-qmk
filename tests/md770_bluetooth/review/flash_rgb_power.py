import sys,json
from pathlib import Path
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from stock_trace import Trace
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_PC,UC_ARM_REG_LR
s=Trace(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()); commands=[];delays=[];power=[]
def hook(cpu,address,size,unused):
 if address==0xd4e4:
  cmd=cpu.reg_read(UC_ARM_REG_R0);n=cpu.reg_read(UC_ARM_REG_R1);r=cpu.reg_read(UC_ARM_REG_R2)
  commands.append({'command':cmd.to_bytes(4,'little')[:n].hex(' '),'read_bytes':r});cpu.reg_write(UC_ARM_REG_R0,0x1640c8 if cmd==0x9f else 0);cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
 elif address==0x8bd0:
  delays.append(cpu.reg_read(UC_ARM_REG_R0));cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
 elif address in [0x8688,0x869c]:power.append([address,cpu.reg_read(UC_ARM_REG_R0)])
s.cpu.hook_add(UC_HOOK_CODE,hook)
s.put(0x20000623,9);s.put(0x20000624,9);s.put(0x20000625,13);s.call(0xd478)
result={'flash_init':{'commands':commands.copy(),'delays_us':delays.copy(),'power_requests':power.copy(),'requested_level':s.get(0x20000623),'actual_level':s.get(0x20000624)}}
commands.clear();delays.clear();s.call(0x47c8,2,1);result['flash_down']={'commands':commands.copy(),'delays_us':delays.copy(),'flag':s.get(0x20000014,4)}
s=Trace(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes())
def track(cpu,access,address,size,value,unused):
 if 0x400b0000<=address<0x400b8000 and address%0x2000 in (0x24,0x28):
  base=address-address%0x2000;old=s.get(base+0x20,4)
  s.put(base+0x20,(old|(value&0xffff))&~(value>>16) if address-base==0x24 else old&~value,4)
s.cpu.hook_add(UC_HOOK_MEM_WRITE,track,begin=0x400b0000,end=0x400b7fff)
def pins():
 out=[]
 for port,pad in [(2,11),(2,12),(2,15),(1,10)]:
  base=0x400b0000+port*0x2000;bit=1<<pad
  d={'pin':chr(65+port)+str(pad),'af':(s.get(0x40022020+port*8+(pad//8)*4,4)>>(pad%8*4))&15}
  for key,offset in [('output',0),('input',4),('pull_up',8),('pull_down',12),('level',32)]:d[key]=bool(s.get(base+offset,4)&bit)
  out.append(d)
 return out
s.call(0x3962,0xe172,3,1);result['rgb_active']=pins();s.call(0x8948);result['rgb_down']=pins()
print(json.dumps(result,indent=2))
