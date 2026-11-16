import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from stock_trace import Trace
firmware = Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
results = []
for dirty in (0, 1):
    s = Trace(firmware)
    s.put(0x20000603, 4)
    s.put(0x20000601, 0)
    s.put(0x20000602, 5)
    s.put(0x20000604, 2)
    s.put(0x20000624, 13)
    s.write(0x200005D8, bytes(8))
    s.put(0x200005B6, dirty)
    s.call(0x9A44)
    results.append({'empty_keyboard_report_dirty': dirty, 'USB_CSR': s.get(0x400A8000,4), 'usb_state': s.get(0x20000601)})
print(json.dumps(results, indent=2))
