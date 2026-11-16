import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk, Stock

qhome = Path('../qmk_firmware').resolve()
elf = qhome / '.build/mistel_md770rgb_bt_right_default_conformance.elf'
payload = elf.read_bytes()
abi = layout(qhome, elf)
firmware = Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
result = {'elf_sha256':hashlib.sha256(payload).hexdigest()}
def pair(level=7):
    q, s = Qmk(payload,abi), Stock(firmware)
    q.write(q.symbol('battery_level'),level,1)
    s.write(0x2000001E,level,1)
    q.matrix()
    s.power()
    return q,s

def samples(q,s,voltage,count):
    q.hardware.voltage_mv=s.hardware.voltage_mv=voltage
    for _ in range(count):
        q.call('md770_power_tick')
        s.call(0x8650)

q,s=pair()
for voltage in (3100,3300,3100):
    samples(q,s,voltage,20)
q.matrix();s.power()
result['interrupted_low_samples']={'qmk_level':q.read(q.symbol('battery_level'),1),'stock_level':s.read(0x2000001E,1),'qmk_filter':q.read(q.symbol('lvd_remaining'),2),'stock_filter':s.read(0x2000001C,2)}
samples(q,s,3100,30)
samples(q,s,3300,1)
q.matrix();s.power()
result['qualified_then_voltage_recovers']={'qmk_level':q.read(q.symbol('battery_level'),1),'stock_level':s.read(0x2000001E,1)}
q,s=pair(1)
samples(q,s,2200,50)
q.matrix();s.power()
result['terminal_level']={'qmk_level':q.read(q.symbol('battery_level'),1),'stock_level':s.read(0x2000001E,1),'qmk_lvd':q.hardware.lvd,'stock_lvd':s.hardware.lvd,'qmk_filter':q.read(q.symbol('lvd_remaining'),2),'stock_filter':s.read(0x2000001C,2)}

q=Qmk(payload,abi)
helper=q.function('usb_driver_set_enabled')
q.hooks.pop(helper,None)
q.usb(True)
q.call(helper,q.symbol('USBD1'),1)
result['idempotent_enable']={'state':q.read(q.symbol('USBD1')+abi['usb_driver_state'],abi['usb_driver_state_bytes']),'configuration':q.read(q.symbol('USBD1')+abi['usb_configuration'],1)}
usb_registers={0x400A8000:0,0x40088104:0}
mmio=[]
access=q.hardware.access
def usb_access(address,size,value=None):
    if address in usb_registers:
        assert size==4
        if value is None:return usb_registers[address]
        usb_registers[address]=value
        mmio.append((hex(address),value))
        return 0
    return access(address,size,value)
q.hardware.access=usb_access
q.hardware.enabled |= 1<<29
q.call(helper,q.symbol('USBD1'),0)
result['actual_usb_disable']={'state':q.read(q.symbol('USBD1')+abi['usb_driver_state'],abi['usb_driver_state_bytes']),'irq29_enabled':bool(q.hardware.enabled&(1<<29)),'writes':mmio}
print(json.dumps(result,indent=2))
