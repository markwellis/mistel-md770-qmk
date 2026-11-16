import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk,Stock
qhome=Path('../qmk_firmware').resolve();p=qhome/'.build/mistel_md770rgb_bt_right_default_conformance.elf';image=p.read_bytes();q=Qmk(image,layout(qhome,p));s=Stock(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes())
s.ready();s.hardware.pin(1,12,True);s.hardware.pin(0,10,False)
for address,value,size in ((0x2000001f,3,1),(0x20000601,1,1),(0x20000603,5,1),(0x20000623,13,1),(0x20000624,13,1),(0x20000625,13,1),(0x20000626,0x10,1),(0x20000628,0,4)):s.write(address,value,size)
for pad in (2,3,4,5):s.hardware.pin(1,pad,pad==2)
s.cpu.mem_write(0x20003e00,bytes([0xfe,*([0xff]*7)]));s.call(0x5d1c,0,0x20003e00)
q.write(q.symbol('raw_matrix')+8,1,1);q.write(q.symbol('matrix')+8,1,1);q.ms=101
q.write(q.symbol('supply'),1,1);q.write(q.symbol('activity'),0)
q.matrix()
result={'elf_sha256':hashlib.sha256(image).hexdigest(),'qmk_remote_row_after_101ms':q.read(q.symbol('raw_matrix')+8,1),'stock_remote_row_before':s.read(0x20000229,1)}
try:
 for i in range(101):
  s.write(0x2000061c,2);s.call(0xda78,budget=1000000)
 result['stock_remote_row_after_101_elapsed_batches']=s.read(0x20000229,1)
except Exception as e:
 result['stock_full_service_boundary']=str(e)
print(json.dumps(result,indent=2))
