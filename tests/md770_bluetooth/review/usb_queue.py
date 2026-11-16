import hashlib, json, shlex, struct, subprocess, sys, tempfile
from pathlib import Path
from io import BytesIO
from elftools.elf.elffile import ELFFile
sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
qhome=Path('../qmk_firmware').resolve()
elf=qhome/'.build/mistel_md770rgb_bt_right_default_conformance.elf'
image=elf.read_bytes(); abi=layout(qhome,elf)
fields={
 'ep_size':'sizeof(usb_endpoint_in_t)', 'ep_queue':'offsetof(usb_endpoint_in_t,obqueue)',
 'ep_config':'offsetof(usb_endpoint_in_t,ep_config)', 'ep_in_state':'offsetof(usb_endpoint_in_t,ep_in_state)',
 'ep_num':'offsetof(usb_endpoint_in_t,config)+offsetof(usb_endpoint_config_t,ep)',
 'ep_timed_out':'offsetof(usb_endpoint_in_t,timed_out)',
 'q_free':'offsetof(output_buffers_queue_t,bcounter)', 'q_suspended':'offsetof(output_buffers_queue_t,suspended)',
 'q_read':'offsetof(output_buffers_queue_t,brdptr)', 'q_write':'offsetof(output_buffers_queue_t,bwrptr)',
 'q_buffers':'offsetof(output_buffers_queue_t,buffers)', 'q_stride':'offsetof(output_buffers_queue_t,bsize)',
 'q_count':'offsetof(output_buffers_queue_t,bn)',
 'usb_config':'offsetof(USBDriver,config)', 'usb_transmitting':'offsetof(USBDriver,transmitting)',
 'usb_in_params':'offsetof(USBDriver,in_params)', 'usb_epc':'offsetof(USBDriver,epc)',
 'tx_size':'offsetof(USBInEndpointState,txsize)',
 'ep_keyboard':'USB_ENDPOINT_IN_KEYBOARD','ep_shared':'USB_ENDPOINT_IN_SHARED',
 'nkro_id':'REPORT_ID_NKRO','keyboard_id':'REPORT_ID_KEYBOARD','count':'USB_ENDPOINT_IN_COUNT',
 'suspend':'USB_EVENT_SUSPEND','wakeup':'USB_EVENT_WAKEUP','reset':'USB_EVENT_RESET'
}
with tempfile.TemporaryDirectory(prefix='md770-usb-queue-') as d:
 p=Path(d); c=p/'abi.c'; o=p/'abi.o'
 c.write_text('#include <stddef.h>\n#include "usb_main.h"\n#include "usb_driver.h"\n#include "usb_endpoints.h"\n#include "report.h"\nconst unsigned review_abi[]={'+','.join(fields.values())+'};\n')
 flags=shlex.split((elf.parent/('obj_'+elf.stem)/'cflags.txt').read_text())
 subprocess.run(['arm-none-eabi-gcc',*flags,'-fno-lto','-c',str(c),'-o',str(o)],cwd=qhome,check=True,capture_output=True)
 section=ELFFile(BytesIO(o.read_bytes())).get_section_by_name('.rodata.review_abi').data()
 a=dict(zip(fields,struct.unpack('<'+'I'*len(fields),section)))
q=Qmk(image,abi); q.usb(True); u=q.symbol('USBD1'); eps=q.symbol('usb_endpoints_in')
q.write(u+a['usb_config'],q.function('usbcfg'))
transmissions=[]
def start_tx():
 ep=q.cpu.reg_read(UC_ARM_REG_R1); p=q.cpu.reg_read(UC_ARM_REG_R2); n=q.cpu.reg_read(UC_ARM_REG_R3)
 transmissions.append({'ep':ep,'data':bytes(q.cpu.mem_read(p,n)).hex()})
 q.write(u+a['usb_transmitting'],q.read(u+a['usb_transmitting'],2)|(1<<ep),2)
 endpoint=q.read(u+a['usb_in_params']+4*(ep-1))
 q.write(endpoint+a['ep_in_state']+a['tx_size'],n)
q.hook('usbStartTransmitI',start_tx)
for i in range(a['count']):
 ep=eps+i*a['ep_size']; q.call('usb_endpoint_in_init',ep)
 number=q.read(ep+a['ep_num'],1)
 q.write(u+a['usb_in_params']+4*(number-1),ep)
 q.write(u+a['usb_epc']+4*number,ep+a['ep_config'])
 q.write(ep+a['ep_queue']+a['q_suspended'],0,1)
def endpoint(index): return eps+index*a['ep_size']
def present(index,report=0): return q.call('usb_endpoint_in_has_report',endpoint(index),report)
def send_key(key):
 q.cpu.mem_write(q.scratch,bytes([0,0,key,0,0,0,0,0])); q.call('send_keyboard',q.scratch)
def complete(index):
 ep=endpoint(index); number=q.read(ep+a['ep_num'],1)
 q.write(u+a['usb_transmitting'],q.read(u+a['usb_transmitting'],2)&~(1<<number),2)
 q.call('usb_endpoint_in_tx_complete_cb',u,number)
def occupied(index):
 queue=endpoint(index)+a['ep_queue']
 return q.read(queue+a['q_count'])-q.read(queue+a['q_free'])
event=q.read(q.function('usbcfg'))
result={'elf_sha256':hashlib.sha256(image).hexdigest(),'boundary':'Actual compiled HAL queues, USB callbacks and report submission; physical USB transmit is captured at usbStartTransmitI.'}
ki=a['ep_keyboard'];si=a['ep_shared']
result['initial_empty']=present(ki)
send_key(4);result['in_flight_present']=present(ki);result['occupied_after_first']=occupied(ki)
complete(ki);result['completed_empty']=present(ki)
for key in (5,6,7): send_key(key);complete(ki)
send_key(8);send_key(9);result['wrapped_occupied']=occupied(ki);result['wrapped_present']=present(ki)
q.usb(True,suspended=True);q.call(event,u,a['suspend']);result['suspended_preserved']=occupied(ki);result['suspended_present']=present(ki)
q.write(u+a['usb_transmitting'],0,2)
q.usb(True);q.call(event,u,a['wakeup']);result['ready_before_sof']=q.call('md770_power_usb_ready')
q.call('usb_sof_isr_kb',u);result['ready_after_sof']=q.call('md770_power_usb_ready')
complete(ki);complete(ki);result['drained_empty']=present(ki)
q.cpu.mem_write(q.scratch,bytes([abi['report_consumer'],1,0]));q.call(q.read(q.symbol('chibios_driver')+abi['driver_extra']),q.scratch)
result['consumer_not_nkro']=present(si,a['nkro_id']);result['consumer_present']=present(si,0)
complete(si)
q.cpu.mem_write(q.scratch,bytes([a['nkro_id'],0])+bytes(abi['nkro_bit_bytes']));q.call(q.read(q.symbol('chibios_driver')+abi['driver_nkro']),q.scratch)
result['nkro_present']=present(si,a['nkro_id']);complete(si);result['nkro_completed_empty']=present(si,a['nkro_id'])
for key in (10,11,12,13): send_key(key)
q.write(endpoint(ki)+a['ep_timed_out'],1,1)
send_key(14);result['timeout_discard_occupied']=occupied(ki);complete(ki);result['timeout_final_complete_empty']=present(ki)
send_key(15);q.usb(False);q.call(event,u,a['reset']);result['reset_discards']=occupied(ki);result['reset_empty']=present(ki)
result['transmissions']=transmissions
print(json.dumps(result,indent=2))
