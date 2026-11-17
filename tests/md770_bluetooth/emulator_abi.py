"""Probe current headers using saved build flags; a matching ELF build is assumed."""

import hashlib
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
         'usb_configured', 'usb_suspended', 'usb_driver_state', 'usb_ready',
         'usb_active', 'usb_driver_suspended', 'usb_init', 'usb_driver_state_bytes',
         'usb_configure_state_bytes', 'report_system', 'report_consumer',
         'record_bytes', 'record_row', 'record_col', 'record_type', 'record_type_bytes',
         'record_pressed', 'key_event', 'macro_keycode', 'driver_keyboard',
         'report_mods', 'report_keys', 'string_prefix', 'string_tap',
         'string_down', 'string_up', 'string_delay', 'macro_count',
         'driver_nkro', 'nkro_mods', 'nkro_bits', 'nkro_bit_bytes',
         'usb_protocol', 'usb_boot_protocol', 'usb_report_protocol', 'usb_protocol_bytes',
         'matrix_rows', 'matrix_cols', 'host_none', 'usb_stop', 'usb_selected',
         'event_bytes', 'event_time', 'record_event', 'select_usb', 'select_bluetooth',
         'bluetooth_profile1', 'driver_extra', 'extra_report_id', 'extra_usage', 'system_tick_hz',
         'momentary_pn', 'momentary_fn', 'pn_layer', 'usb_event_wakeup', 'usb_event_configured',
         'endpoint_bytes', 'endpoint_queue', 'endpoint_config', 'endpoint_in_state',
         'endpoint_number', 'endpoint_timed_out', 'queue_free', 'queue_suspended', 'queue_count',
         'usb_driver_config', 'usb_transmitting', 'usb_in_params', 'usb_epc', 'usb_tx_size',
         'keyboard_endpoint', 'shared_endpoint', 'report_nkro', 'in_endpoint_count',
         'usb_event_suspend', 'usb_event_reset', 'out_endpoint_count', 'out_endpoint_bytes',
         'out_endpoint_queue', 'out_endpoint_config', 'out_endpoint_number',
         'out_queue_suspended', 'usb_out_params', 'usb_receiving',
         'radio_phase_bytes', 'radio_ready', 'radio_failed', 'radio_off',
         'radio_command_bytes', 'radio_stop_command', 'radio_no_command',
         'radio_keyboard_command', 'radio_system_command', 'eeconfig_keyboard', 'eeprom_logical_size']


def firmware_binary(elf_path, image):
    with TemporaryDirectory(prefix='md770-binary-') as temporary:
        source = Path(temporary) / 'application.elf'
        target = Path(temporary) / 'application.bin'
        source.write_bytes(image)
        subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', str(source), str(target)],
                       check=True, capture_output=True, text=True)
        image = target.read_bytes()
    if elf_path.with_suffix('.bin').read_bytes() != image:
        raise ValueError('The candidate binary differs from the tested ELF application')
    return image


def layout(qmk, elf_path, *, provenance=None):
    image = elf_path.read_bytes()
    firmware = ELFFile(BytesIO(image))
    if firmware['e_machine'] != 'EM_ARM':
        raise ValueError('The ABI probe requires an ARM ELF')
    flags_path = elf_path.parent / ('obj_' + elf_path.stem) / 'cflags.txt'
    saved_flags = flags_path.read_text()
    flags = shlex.split(saved_flags)
    source = Path(__file__).with_suffix('.c').resolve()
    with TemporaryDirectory(prefix='md770-abi-') as temporary:
        target = Path(temporary) / 'layout.o'
        subprocess.run(['arm-none-eabi-gcc', *flags, '-fno-lto', '-c', str(source), '-o', str(target)],
                       cwd=qmk, check=True, capture_output=True, text=True)
        binary = ELFFile(BytesIO(target.read_bytes()))
        section = binary.get_section_by_name('.rodata.emulator_abi')
        if provenance is not None:
            compiler = subprocess.run(['arm-none-eabi-gcc', '--version'], check=True,
                                      capture_output=True, text=True)
            preprocessed = subprocess.run(['arm-none-eabi-gcc', *flags, '-E', '-P', str(source)],
                                          cwd=qmk, check=True, capture_output=True)
            provenance.update({
                'assumption': 'Current headers and compiler must match the supplied ELF build; rebuild after changes',
                'elf_sha256': hashlib.sha256(image).hexdigest(),
                'compiler': compiler.stdout.splitlines()[0],
                'flags_sha256': hashlib.sha256(saved_flags.encode()).hexdigest(),
                'preprocessed_probe_sha256': hashlib.sha256(preprocessed.stdout).hexdigest(),
            })
        result = dict(zip(NAMES, struct.unpack('<' + 'I' * len(NAMES), section.data()), strict=True))
        result['nkro_mask'] = int.from_bytes(binary.get_section_by_name('.rodata.emulator_nkro_flag').data(), 'little')
        return result
