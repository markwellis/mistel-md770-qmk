import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk,Stock
qhome=Path('../qmk_firmware').resolve();elf=qhome/'.build/mistel_md770rgb_bt_right_default_conformance.elf';image=elf.read_bytes();abi=layout(qhome,elf);b=Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
def pair():
 q=Qmk(image,abi);s=Stock(b);q.ms=599000;q.write(q.symbol('activity'),0);q.write(q.symbol('radio_state'),3,1);q.write(q.symbol('radio_mode'),1,1);q.write(q.symbol('pairing'),1,1);q.write(q.symbol('radio_phases'),680,2);q.write(q.symbol('radio_interval'),1000,2)
 for a,v,z in ((0x2000068c,2,1),(0x20000027,2,1),(0x20000021,1,1),(0x200000c0,4,1),(0x200000c2,680,2),(0x200000c8,1000,2),(0x200023ec,2000,4),(0x200001e4,3,1)):s.write(a,v,z)
 return q,s
q,s=pair();q.call('connection_set_host',abi['host_usb']);s.cpu.mem_write(0x20003e00,bytes([0x3b,1,0,1]));s.call(0x5ef8,0x20003e00);q.indicators();s.call(0x634c)
result={'elf_sha256':hashlib.sha256(image).hexdigest(),'manual_usb':{'qmk_pairing':q.read(q.symbol('pairing'),1),'stock_pairing':s.read(0x20000021,1),'qmk_idle_remaining_ms':600000-(q.ms-q.read(q.symbol('activity'))),'stock_idle_remaining_ms':s.read(0x200023ec)//2,'stock_output':s.read(0x2000068c,1)}}
q,s=pair();q.write(q.symbol('radio_phases'),0,2);s.write(0x200000c2,0,2);q.write(q.symbol('activity'),q.ms-10000);s.write(0x200023ec,1180000);q.write(q.symbol('radio_state'),4,1);s.write(0x200001e4,4,1);q.indicators();s.call(0x5ce4);s.call(0x634c)
result['connected_after_last_edge']={'qmk_pairing':q.read(q.symbol('pairing'),1),'stock_pairing':s.read(0x20000021,1),'qmk_idle_remaining_ms':600000-(q.ms-q.read(q.symbol('activity'))),'stock_idle_remaining_ms':s.read(0x200023ec)//2}
print(json.dumps(result,indent=2))
