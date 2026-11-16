from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm_const import ARM_OP_MEM, ARM_REG_PC
import hashlib
import sys

b = Path('mistel_md770rgb_bt_left_stock.bin').read_bytes()
assert hashlib.sha256(b).hexdigest() == 'febc84d9dc1fd23152218232839279ecb59f255615a6d6c5b4d951a848c85064'
c = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
c.detail = True
ranges = [(int(a,16),int(b,16)) for a,b in (arg.split(':') for arg in sys.argv[1:])] if len(sys.argv)>1 else [(0x67D4,0x68B0),(0x4C20,0x4C98),(0x4CF8,0x4DFC),(0x532C,0x53BC),(0x9D2C,0x9DA8)]
for start, end in ranges:
    for i in c.disasm(b[start-0x3200:end-0x3200],start):
        extra = ''
        if i.mnemonic=='ldr' and len(i.operands)>1 and i.operands[1].type==ARM_OP_MEM and i.operands[1].mem.base==ARM_REG_PC:
            a=((i.address+4)&~3)+i.operands[1].mem.disp
            extra = f' ; [{a:04x}]={int.from_bytes(b[a-0x3200:a-0x3200+4],"little"):08x}'
        print(f'{i.address:04x} {i.mnemonic:7} {i.op_str}{extra}')
