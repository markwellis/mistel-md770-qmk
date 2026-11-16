"""Shared macro scenarios and measured pair coverage for hardware calibration."""

from itertools import combinations, product

FACTORS = {
    'transport': ('usb', 'bluetooth'),
    'trigger_half': ('left', 'right'),
    'macro_kind': ('text', 'chord', 'delay'),
    'modifier': ('none', 'shift', 'control'),
    'connection': ('steady', 'reconnected'),
}
MODIFIERS = {'none': None, 'shift': 0xE1, 'control': 0xE0}
TRIGGERS = {
    'left': {'text': ('Q', 8, 1), 'chord': ('W', 15, 2), 'delay': ('E', 15, 3)},
    'right': {'text': ('U', 1, 1), 'chord': ('I', 2, 1), 'delay': ('O', 3, 1)},
}


def all_cases():
    return [dict(zip(FACTORS, values, strict=True)) for values in product(*FACTORS.values())]


def expected_events(case):
    held = MODIFIERS[case['modifier']]
    events = [(held, True)] if held is not None else []
    if case['macro_kind'] == 'chord':
        if held != 0xE0:
            events.append((0xE0, True))
        events.extend(((4, True), (4, False)))
        if held != 0xE0:
            events.append((0xE0, False))
    else:
        keys = (4, 5, 6) if case['macro_kind'] == 'text' else (4, 5)
        events.extend(event for key in keys for event in ((key, True), (key, False)))
    if held is not None:
        events.append((held, False))
    return events


def macro_data(case, abi):
    def command(name, code):
        return bytes([abi['string_prefix'], abi['string_' + name], code])

    if case['macro_kind'] == 'chord':
        events = (('down', 0xE0), ('down', 4), ('up', 4), ('up', 0xE0))
    else:
        keys = (4, 5, 6) if case['macro_kind'] == 'text' else (4, 5)
        events = tuple(event for key in keys for event in (('down', key), ('up', key)))
    data = bytearray()
    for index, (name, code) in enumerate(events):
        data.extend(command(name, code))
        if index + 1 < len(events):
            delay = 100 if case['macro_kind'] == 'delay' and index == 1 else 40
            data.extend(bytes([abi['string_prefix'], abi['string_delay']]) + str(delay).encode() + b'|')
    return bytes(data) + b'\x00'


def value_pairs(case):
    return {((left, case[left]), (right, case[right])) for left, right in combinations(FACTORS, 2)}


def hardware_plan():
    from allpairspy import AllPairs

    rows = [dict(zip(FACTORS, values, strict=True)) for values in AllPairs(list(FACTORS.values()))]
    required = set().union(*(value_pairs(case) for case in all_cases()))
    covered = set().union(*(value_pairs(case) for case in rows))
    if covered != required:
        raise ValueError('The generated hardware set does not cover every factor-value pair')
    rows.sort(key=lambda case: tuple(FACTORS[name].index(case[name]) for name in
                                    ('transport', 'connection', 'macro_kind', 'trigger_half', 'modifier')))
    return {
        'scope': 'Macro host key events for the listed factors; physical timing and radio delivery require measurement',
        'factors': FACTORS,
        'software_combinations': len(all_cases()),
        'required_pairs': len(required),
        'covered_pairs': len(covered),
        'macro_recordings': {
            'text': 'Record a, b, c; the recorder supplies the normal 40 ms intervals.',
            'chord': 'Record Left Ctrl down, a down/up, Left Ctrl up.',
            'delay': 'Record a, tap Fn+G once, then b; this inserts 100 ms before b.',
        },
        'cases': [dict(id=f'HC{index:02}', **case,
                       trigger_key=TRIGGERS[case['trigger_half']][case['macro_kind']][0],
                       expected_key_events=expected_events(case))
                  for index, case in enumerate(rows, 1)],
    }
