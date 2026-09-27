#!/usr/bin/env python3
"""Read the emitted LLVM for bitstream-nv's allocation probe and say
whether any function in `bitstream_core` can put a cell on
the heap.

Run by tests/alloc_scan.sh three times: once on the package as it
stands, and twice on copies with an allocation spliced into the core.
Those two copies are what the scan and the compiler respectively have to
catch, because a check that cannot fail is not a check.

The IR is emitted at `--opt=0` on purpose.  At the default optimisation
level the whole probe inlines into `novo_main`, there is no function
left to attribute an allocation to, and the scan would pass over an
empty file.
"""
import re
import sys

# Every way a function can put a cell on the heap.  Any runtime entry
# point with `alloc` in its name is the direct one: `novo_alloc_rc` for
# a struct or a boxed value, `novo_vec_alloc_n_i64` for a list literal.
# The four in BOXERS allocate inside the runtime, so a search for the
# first kind alone would call a per-character boxing loop
# allocation-free.  `novo_str_byte_at` reaches `novo_some_int`, which
# reaches `novo_alloc_atomic`, and none of that is visible in the
# caller's IR.
ALLOCATOR = re.compile(r'call [^\n]*@(novo_\w*alloc\w*)\(')
BOXERS = ['novo_some_int', 'novo_some_float',
          'novo_str_byte_at(', 'novo_bytes_byte_at(']

# The other modules are not matched.  They allocate, which is what they
# are for, and the half that runs on a device is the half this scan is
# about.
CORE = re.compile(r'^novo_user_bitstream_core_')

FNS = re.compile(r'^define[^\n]*?@([A-Za-z0-9_.]+)\([^\n]*\{\n(.*?)\n\}',
                 re.S | re.M)

# The module has nineteen `pub fn`s and six private helpers, and
# the probe reaches every one.  Fewer than this in the IR means the
# probe or the name scheme moved, and that the scan is measuring
# nothing.
FLOOR = 25


def main(path):
    src = open(path).read()
    seen, offenders = 0, []
    for m in FNS.finditer(src):
        name, body = m.group(1), m.group(2)
        if not CORE.match(name):
            continue
        seen += 1
        for m2 in ALLOCATOR.finditer(body):
            offenders.append('%s: %s' % (name, m2.group(1)))
        for boxer in BOXERS:
            if 'call' in body and ('@' + boxer) in body:
                offenders.append('%s: %s' % (name, boxer.rstrip('(')))
    if seen < FLOOR:
        print('FAIL only %d core function(s) in the IR, expected at least '
              '%d — the probe or the name scheme moved, and this check was '
              'measuring nothing' % (seen, FLOOR))
    elif offenders:
        print('FAIL ' + '; '.join(sorted(set(offenders))))
    else:
        print('OK %d function(s) in bitstream_core, zero heap cells' % seen)


if __name__ == '__main__':
    main(sys.argv[1])
