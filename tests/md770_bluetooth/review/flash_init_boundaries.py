import json,sys
from pathlib import Path
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from stock_trace import Trace
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_PC,UC_ARM_REG_LR
results=[]
for bad_ids,busy in ((0,0),(2,2),(1024,600)):
 s=Trace(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()); commands=[];delays=[];ids=0;status=0
 def hook(cpu,address,size,unused):
  global ids,status
  if address==0xd4e4:
   cmd=cpu.reg_read(UC_ARM_REG_R0);n=cpu.reg_read(UC_ARM_REG_R1);r=cpu.reg_read(UC_ARM_REG_R2)
   commands.append((cmd.to_bytes(4,'little')[:n].hex(' '),r))
   reply=0
   if cmd==0x9f:
    reply=0 if ids<bad_ids else 0x1340c8;ids+=1
   elif cmd==5:
    reply=int(status<busy);status+=1
   cpu.reg_write(UC_ARM_REG_R0,reply);cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
  elif address==0x8bd0:
   delays.append(cpu.reg_read(UC_ARM_REG_R0));cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
 s.cpu.hook_add(UC_HOOK_CODE,hook)
 s.cpu.reg_write(UC_ARM_REG_LR,0x10001);s.cpu.emu_start(0xd479,0x10000,count=100000)
 assert s.cpu.reg_read(UC_ARM_REG_PC)==0x10000
 results.append({'bad_IDs_supplied':bad_ids,'busy_reads_supplied':busy,'ID_reads':ids,'AB_count':commands.count(('ab',0)),'write_enable_count':commands.count(('06',0)),'write_status_count':commands.count(('01 02 00',0)),'status_reads':status,'10us_waits':delays.count(10),'100us_waits':delays.count(100),'flag_after_return':s.get(0x20000014,4),'first_commands':commands[:8],'last_commands':commands[-4:]})
print(json.dumps({'boundary':'Actual d478 and9c68 instructions; d4e4 SPI transaction results and8bd0 delays supplied.','cases':results},indent=2))
