"""Read the Linux start token written by native Claude Code."""

import re
from pathlib import Path


def process_start_ticks(pid):
    if type(pid) is not int or pid <= 0:
        raise OSError('invalid process identity')
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
    except FileNotFoundError:
        return None
    # comm can contain spaces and parentheses; field 22 follows its final ')'.
    fields = stat.rpartition(')')[2].split()
    if (not stat.startswith(f'{pid} (') or len(fields) < 20 or
            not re.fullmatch(r'[0-9]+', fields[19])):
        raise OSError('process identity unavailable')
    return fields[19]
