# Changelog

Every published version, newest first. This file is on the publish
allow-list, so it travels with the package: it is the only thing a
consumer deciding whether to upgrade can read.

## 0.1.1 — 2026-11-03

This release requires novo 0.23.0 or later.

## 0.1.0 — 2026-09-27

The first implementation of the interface published as 0.0.1 and
0.0.2: the accumulator and the sink in both bit orders, and a reader
and a writer over `Bytes`.

- `bitstream_core` carries `@tier(embedded)` on every function and
  puts nothing on the heap.  `tests/embedded_probe.nv` runs under QEMU
  and checks reads and writes in both orders, and `tests/alloc_scan.sh`
  reads the emitted LLVM for a call to the allocator.
- `bitstream.read`, `peek` and `skip` split a read wider than 56 bits
  into two.  The accumulator is refilled a byte at a time, so at an
  offset that is not a byte boundary it holds 64 bits less those
  already taken from the current byte; a `bitstream_core` caller
  reading a field that wide at such an offset takes it in two parts.
- `bitstream.read` refuses a read past the end with the reader the
  caller holds unchanged, and pulls in only as many bytes as the read
  needs, so `reader_acc` after a three-bit read of a fresh reader holds
  five bits.
- A `bitstream.write` that completes a byte copies the writer's byte
  list, so the writer passed in keeps its bytes.  A long stream is
  written through `bitstream_core.put`.

## 0.0.2 — 2026-09-15

README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

## 0.0.1 — 2026-09-11

The **interface**, before anyone implements it.  Every signature, every
type and every effect row is published; every body is `todo()`, and the
release is stamped `NOT IMPLEMENTED — interface only`.  Adding this
package works and calling it panics.

- Two modules.  `bitstream_core` is the accumulator alone — `order`,
  `hold` and `count` in a `@value` struct, no buffer and no allocation;
  `bitstream` is that accumulator with a `Bytes` source and a byte sink
  attached, for a caller who has the whole payload already.
- Both bit orders, chosen at the constructor and not per call.
  LSB-first is DEFLATE's; MSB-first is everything else's.  The README
  carries the table of which format wants which, including DEFLATE's
  own split — data elements LSB-first, Huffman codes MSB-first, in the
  same stream.
- Read, peek, skip, align, and the position and remaining counts, in
  bits.  Peek and skip are separate calls because a Huffman decoder
  peeks the longest code its table holds and then skips exactly the
  length the table says, and a bit stream has no way to put bits back.
- The writer's mirror: write, pad to a boundary, and ask how many bits
  have been taken.  A value with a bit set above its field is refused
  rather than masked — masking writes a document that decodes to a
  different number with nothing to show for it.
- `reader_acc` and `writer_sink`, the handoff between the halves: a
  host that parsed a header hands the state to a loop that allocates
  nothing and compiles for a device.

**The device claim is built.**  `tests/embedded_probe.nv` compiles to a
Cortex-M4 ELF for `--target=nrf52-qemu`, driving the accumulator and the
sink a byte at a time the way an interrupt handler would.  `bitstream`
is outside the probe on purpose: it speaks `Bytes`, and one host-only
function anywhere in a compilation unit is an undefined symbol at
embedded link time whether or not the firmware calls it.

**Two shapes the language chose rather than the format.**  `BitTake`
and `BitEmit` answer `ok: Bool` instead of a `Result`, because a
`@value` struct cannot be a `Result` payload and a bit reader that
allocated to report a refill boundary would allocate once per byte of a
compressed stream.  And `BitReader` spells `order`, `hold` and `count`
out rather than holding a `BitAcc`, because a `@value` struct may not be
a field of a boxed struct.

**No dependencies.**  Shifting an integer needs the language and nothing
else, and a dependency here would be a dependency of every compression
codec on the grid.
