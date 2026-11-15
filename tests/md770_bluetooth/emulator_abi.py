"""Read structure offsets using the same compiler flags as the firmware."""

from io import BytesIO
from pathlib import Path
import shlex
import struct
import subprocess
from tempfile import TemporaryDirectory

from elftools.elf.elffile import ELFFile

NAMES = ['usb_configuration', 'usb_status', 'usb_configure_state',
         'pwm_state', 'pwm_config', 'pwm_period', 'pwm_channels', 'pwm_timer',
         'pwm_stop', 'pwm_ready', 'gpt_state', 'gpt_config', 'gpt_timer',
         'gpt_continuous', 'gpt_counter_bytes', 'host_usb', 'host_bluetooth',
         'usb_configured', 'usb_suspended']


def layout(qmk, elf_path):
    flags_path = elf_path.parent / ('obj_' + elf_path.stem) / 'cflags.txt'
    flags = shlex.split(flags_path.read_text())
    source = Path(__file__).with_suffix('.c').resolve()
    with TemporaryDirectory(prefix='md770-abi-') as temporary:
        target = Path(temporary) / 'layout.o'
        subprocess.run(['arm-none-eabi-gcc', *flags, '-fno-lto', '-c', str(source), '-o', str(target)],
                       cwd=qmk, check=True, capture_output=True, text=True)
        binary = ELFFile(BytesIO(target.read_bytes()))
        section = binary.get_section_by_name('.rodata.emulator_abi')
        return dict(zip(NAMES, struct.unpack('<' + 'I' * len(NAMES), section.data()), strict=True))
