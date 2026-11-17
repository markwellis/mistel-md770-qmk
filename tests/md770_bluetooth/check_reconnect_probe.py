from pathlib import Path
import hashlib
import json
import struct
import sys
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk
qmk=Path('../qmk_firmware').resolve()
elf=qmk/'.build/mistel_md770rgb_bt_right_markwellis_reconnect_diagnostics_v2.elf'
abi=layout(qmk,elf)
machine=Qmk(elf.read_bytes(),abi)
machine.start()
machine.hardware.spi.errors=0x80
machine.poll()
machine.task()
scratch=machine.scratch
machine.call('md770_reconnect_diag',0,0,scratch)
stats=struct.unpack('<7I',machine.cpu.mem_read(scratch,28))
count=stats[-1]
assert count>0
machine.call('md770_reconnect_diag',3+(count-1)%4,0,scratch)
record=struct.unpack('<I8BH7s7s',machine.cpu.mem_read(scratch,28))
assert record[1]==3,record
assert record[9]&0x80,record
machine=Qmk(elf.read_bytes(),abi)
machine.call('reset_radio')
machine.write(machine.symbol('pending_command'),0x80,1)
machine.task(1000)
machine.task(1500)
machine.task(10)
assert machine.transfer(bytes(4)) == [0xa7,2,0,2]
machine.transfer(bytes.fromhex('b6 00 03'))
machine.drain()
machine.select(1)
machine.call('md770_reconnect_diag',36,0,machine.scratch)
packets=machine.drain()
assert packets == [[0xaa,3,1],[0xa1]+[0]*8,[0xa3,0],[0xa2]+[0]*4],packets
assert not machine.connected()
print(json.dumps({'diagnostic_elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'spi_error_injected':128,'diagnostic_event':record[1],'diagnostic_status':record[9],'latched_error_preserved':True,'stock_empty_report_batch':packets,'connected_status_injected_for_report_batch':False}))
