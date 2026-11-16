import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_macros import MacroQmk
from emulator_firmware import Stock
from unicorn import UC_HOOK_CODE
qhome=Path('../qmk_firmware').resolve();elf=qhome/'.build/mistel_md770rgb_bt_right_default_conformance.elf';image=elf.read_bytes();abi=layout(qhome,elf)
q=MacroQmk(image,abi);q.output_mode(False);q.hardware.pin(1,12,True);q.hardware.pin(0,10,False);q.write(q.symbol('supply'),3,1)
fn=q.read(q.symbol('chibios_driver')+abi['driver_keyboard'])&~1;q.hooks.pop(fn)
endpoint=fn
calls=[];switched=False
def interrupt(cpu,a,z,c):
 global switched
 if a==fn and not switched:
  switched=True;q.usb(True,suspended=True);calls.append('suspend_between_hook_and_driver')
 if a==endpoint:calls.append('actual_send_keyboard')
q.cpu.hook_add(UC_HOOK_CODE,interrupt)
q.call('register_code',4)
result={'elf_sha256':hashlib.sha256(image).hexdigest(),'pending_after_failed_submission':q.read(q.symbol('usb_pending'),1),'latest_keyboard':bytes(q.cpu.mem_read(q.symbol('latest_keyboard'),8)).hex()}
q.call('md770_power_task');q.usb(True);q.call('md770_power_task');result['calls_after_resume']=calls;result['pending_after_resume']=q.read(q.symbol('usb_pending'),1)
s=Stock(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes());s.write(0x2000068c,1,1);s.write(0x20000601,0,1);s.cpu.mem_write(0x20003e00,bytes([4,0,0,1]));s.call(0x56a8,0x20003e00);result['stock_usb_pending_after_key']=s.read(0x200005b6,1)
print(json.dumps(result,indent=2))
