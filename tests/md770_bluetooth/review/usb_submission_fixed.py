from pathlib import Path
p=Path(__file__).with_name('usb_queue.py')
source=p.read_text(); exec(source[:source.index("result={'elf_sha256'")])
from unicorn import UC_HOOK_CODE
q.set_host('host_usb');q.write(q.symbol('active_host'),abi['host_usb'],1)
q.write(q.symbol('driver'),q.symbol('chibios_driver'))
q.hardware.pin(1,12,True);q.hardware.pin(0,10,False);q.write(q.symbol('supply'),3,1)
fn=q.symbol('send_keyboard'); switched=False
def inject(cpu,address,size,unused):
 global switched
 if address==fn and not switched:
  switched=True;q.usb(True,suspended=True)
handle=q.cpu.hook_add(UC_HOOK_CODE,inject)
q.call('register_code',4);q.cpu.hook_del(handle)
result={'elf_sha256':hashlib.sha256(image).hexdigest(),'pending_after_rejected_submission':q.read(q.symbol('usb_pending'),1),'queue_after_rejection':occupied(a['ep_keyboard']),'latest_keyboard':bytes(q.cpu.mem_read(q.symbol('latest_keyboard'),8)).hex()}
q.call('md770_power_task')
q.usb(True);q.call(event,u,a['wakeup']);q.call('md770_power_task')
result['pending_before_sof']=q.read(q.symbol('usb_pending'),1);result['queue_before_sof']=occupied(a['ep_keyboard'])
q.call('usb_sof_kb',u);q.call('md770_power_task')
result['pending_after_sof']=q.read(q.symbol('usb_pending'),1);result['queue_after_sof']=occupied(a['ep_keyboard']);result['transmissions']=transmissions
print(json.dumps(result,indent=2))
