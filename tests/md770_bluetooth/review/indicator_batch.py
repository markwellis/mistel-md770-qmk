import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk,Stock
qhome=Path('../qmk_firmware').resolve(); elf=qhome/'.build/mistel_md770rgb_bt_right_default_conformance.elf'; image=elf.read_bytes();abi=layout(qhome,elf); stock_image=Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
print('ELF',hashlib.sha256(image).hexdigest())
ADDR=(0x4006e098,0x4002c09c)
def pair():
 q=Qmk(image,abi);s=Stock(stock_image);s.write(0x2000068c,2,1)
 assert 'radio_countdown' in q.symbols
 return q,s
def outputs(q,s,label):
 a=[q.hardware.registers[x] for x in ADDR];b=[s.hardware.registers[x] for x in ADDR]
 print(json.dumps({'case':label,'qmk':a,'stock':b,'matches':a==b}))
def service(q,s,elapsed=0):
 q.ms+=elapsed;q.indicators();s.write(0x2000002a,max(0,s.read(0x2000002a,2)-elapsed*2),2);s.indicators(elapsed*2)
def indicate(q,s,pairing=False):
 q.write(q.symbol('radio_mode'),1,1);q.write(q.symbol('pairing'),int(pairing),1);q.write(q.symbol('radio_phases'),680 if pairing else 4,2);q.write(q.symbol('radio_interval'),1000 if pairing else 500,2);s.write(0x200000c0,4,1);s.write(0x200000c2,680 if pairing else 4,2);s.write(0x200000c8,1000 if pairing else 500,2)
q,s=pair();q.write(q.symbol('eligible'),1,1);s.write(0x20000020,1,1);q.hardware.pin(2,13,True);s.hardware.pin(2,13,True);service(q,s);q.hardware.pin(2,13,False);s.hardware.pin(2,13,False);service(q,s,1000);outputs(q,s,'first_burst_at_1000')
q,s=pair();indicate(q,s);service(q,s);service(q,s,250);service(q,s,100);indicate(q,s);service(q,s);outputs(q,s,'reselect_off_350');service(q,s,150);outputs(q,s,'reselect_nextedge_500')
q,s=pair();q.write(q.symbol('supply'),1,1);q.write(q.symbol('battery_level'),4,1);s.write(0x2000001f,1,1);s.write(0x2000001e,4,1);indicate(q,s,True);service(q,s);outputs(q,s,'pairing_low_battery')
q,s=pair();q.write(q.symbol('eligible'),1,1);s.write(0x20000020,1,1);q.hardware.pin(2,13,True);s.hardware.pin(2,13,True);service(q,s);q.write(q.symbol('eligible'),0,1);s.write(0x20000020,0,1);q.write(q.symbol('supply'),1,1);q.write(q.symbol('battery_level'),4,1);s.write(0x2000001f,1,1);s.write(0x2000001e,4,1);service(q,s);outputs(q,s,'charge_steady_to_low_battery')
q,s=pair();q.write(q.symbol('radio_leds'),2,1);s.write(0x2000068b,2,1);s.write(0x2000002a,4000,2);indicate(q,s);service(q,s);outputs(q,s,'caps_over_selection');service(q,s,2000);outputs(q,s,'late_single_edge_only')
