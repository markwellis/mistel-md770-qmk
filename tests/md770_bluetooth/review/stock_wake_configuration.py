from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('tests/md770_bluetooth').resolve()))
from stock_trace import Trace
b=Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
for a,n in ((0xe100,48),(0xe631,54)):
 print(hex(a),b[a-0x3200:a-0x3200+n].hex(' '))
for mode in (0,1,2):
 s=Trace(b)
 s.call(0xab04,mode)
 print('mode',mode,'writes',json.dumps(s.mmio))
 print('AFIO',[hex(s.get(0x40022000+i,4)) for i in (0,4)],'EXTI',[hex(s.get(0x40024040+i,4)) for i in (0x10,0x14,0x18)])
 print('GPIO',[[hex(s.get(0x400b0000+p*0x2000+i,4)) for i in (0,4,8,0xc,0x10,0x14,0x18,0x1c)] for p in range(4)])
