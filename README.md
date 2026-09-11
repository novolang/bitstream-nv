# bitstream-nv

**Status: NOT IMPLEMENTED — interface only.**

Every public function below is published with its signature and its
effect row, and every body is `todo()`.  Installing this package works;
calling it panics with `not implemented`.

## What this is

Values that are not a whole number of bytes: read 1 to 64 bits at a
time out of bytes a caller already holds, and write them back.  Peek
without consuming, skip without reading, align to a byte boundary, and
ask where you are — in bits, because bits are the only position a bit
stream has.

Two modules, and the split is the point.  `bitstream_core` is the
accumulator on its own — two integers and an order in a `@value` struct,
no buffer, no allocation, and it compiles for a Cortex-M.
`bitstream` is that accumulator with a `Bytes` source and a byte sink
attached, for a caller who already has the whole payload and does not
want to write the refill loop.

## Which bit order a format wants

This is the fact a reader of this package came for, so it is a table.

| format | order | where it says so |
| --- | --- | --- |
| DEFLATE, zlib, gzip — everything but the Huffman codes | **LSB-first** | RFC 1951 § 3.1.1 |
| DEFLATE's Huffman codes, inside that same stream | **MSB-first** | RFC 1951 § 3.1.1 |
| JPEG entropy-coded segments | **MSB-first** | ITU-T T.81 § F.1.2.1 |
| PNG sub-byte pixel rows (1, 2, 4 bpp) | **MSB-first** | RFC 2083 § 7.2 |
| Brotli | **LSB-first** | RFC 7932 § 1.2 |
| LZMA / xz range coder | **MSB-first** | the xz format specification § 4 |
| protocol field diagrams drawn left to right | **MSB-first** | every RFC that draws one |

**DEFLATE's split is not a mistake in the table.**  RFC 1951 packs data
elements starting from the least-significant bit, and Huffman codes
starting from the most-significant bit of the code, in the same stream.
An inflater therefore reads its block header, its lengths and its extra
bits LSB-first and its codes MSB-first — which in practice is done by
reading the code LSB-first and reversing it, because reversing a short
code is cheaper than running two accumulators.  A decoder built on this
package does the same: one `BitsLsbFirst` reader, and the code reversal
in the Huffman table where it belongs.

Everything else in the table is MSB-first, which is why the order is a
constructor argument with no default.  A stream read in the wrong order
does not fail — it answers plausible numbers — and that is the failure
this package's shape exists to make hard to reach by accident.

## Adding it, and checking it

```bash
novo pkg add bitstream-nv     # into your novo.toml
novo pkg build                # type- and effect-check the package
novo test --isolate tests/bitstream_tests.nv
```

`novo test` is red today and that is the point of the release: every
assertion fails with `not implemented: bitstream.<fn>`.  They turn green
one at a time as bodies land.

## The one example that will work

The first three bits of every DEFLATE stream: BFINAL, then the two bits
of BTYPE, both LSB-first (RFC 1951 § 3.2.3).

```novo
use std.bytes
use bitstream

fn main() [io]
    let r = bitstream.reader(bytes.from_hex("0300") ?? bytes.zeros(0), BitsLsbFirst)
    match bitstream.read(r, 1)
        Err(e)   => println(e.message())
        Ok(last) =>
            match bitstream.read(last.reader, 2)
                Err(e)    => println(e.message())
                Ok(kind)  => println("final=${last.value} type=${kind.value}")
                            // final=1 type=1 — a final fixed-Huffman block
```

## The load-bearing interface

`BitAcc` and its three fields, in `bitstream_core`:

```novo
pub @value
struct BitAcc
    order: Int
    hold: Int
    count: Int
```

Everything else in the package is that value with something attached.
The host reader is `BitAcc` plus a `Bytes` and a byte index; the host
writer is its mirror plus a list of finished bytes; `reader_acc` and
`writer_sink` hand the value back so a program that parsed a header on
the host can run the inner loop on a device.

Three consequences a reviewer should push on:

- **The order is a field, not two function families.**  A stream is one
  order from end to end, so the choice is made once at the constructor.
  Two families would let a caller feed LSB-first and take MSB-first with
  no diagnostic.
- **The device half answers a flag, not a `Result`.**  `BitTake` and
  `BitEmit` carry `ok: Bool`.  A `@value` struct cannot be a `Result`
  payload, and a bit reader that allocated to report a refill boundary
  would allocate once per byte of a compressed stream.  The host half
  does answer `Result<_, BitError>`, because by then the allocation has
  already happened.
- **The accumulator is spelled twice.**  `BitReader` holds `order`,
  `hold` and `count` as its own fields rather than holding a `BitAcc`: a
  `@value` struct may not be a field of a boxed struct.  The composition
  that would read best is the one the language refuses, and the two
  halves are kept in step by `bitstream_core`'s rules being the only
  rules.

## The layer, and why

`core`.  Everything here is shifting and masking integers the caller
already holds, and no function declares an effect — a bit accumulator
has nowhere to put one.

It carries `tests/embedded_probe.nv`, so the device claim is **built**
rather than asserted: `bitstream_core` speaks `Int` and `u8` and nothing
else, and the probe compiles to a Cortex-M4 ELF for
`--target=nrf52-qemu`.  `bitstream` is deliberately outside the probe —
it speaks `Bytes`, the embedded runtime defines no `novo_bytes_*`
symbol, and one host-only function anywhere in a compilation unit is an
undefined symbol at embedded link time whether or not the firmware calls
it.

## Where it sits beside the compression codecs

This package exists because the codecs that need it each wrote it again.
flate-nv's `DeflateState` and `InflateState` both carry a `bit_buf` and a
`bit_count`; a PNG reader unpacking 4-bit rows carries the same pair; so
would a JPEG decoder, an LZMA decoder and a Brotli decoder.  That is one
encoding kept in step in five places, and the fifth copy is the one that
gets the fix the first four got.

So the intended shape after implementation is that a compression codec
depends on this and deletes its own accumulator.  Nothing forces it —
the codecs are published already and their bit state is private — but
the interface here is deliberately the shape theirs already have, so the
change is a substitution rather than a redesign.

## A read of 64 bits answers a signed number

The value travels in an `Int`, which is 64 bits and signed, so a read of
64 whose top bit is set answers a negative number.  That is the bit
pattern and not a fault.  A caller who wants the unsigned reading reads
32 and 32 and combines them.  No format in the table above reads a
64-bit field, so this is a corner rather than a limitation — but it is
the sort of corner that is cheaper to write down than to find.

## The reference implementation

`bitvec` (Rust, MIT) and `bitstring` (Python, MIT) for the surface, and
the format specifications in the table above for the vectors.  Every
assertion in `tests/bitstream_tests.nv` is a byte from one of those
specifications with the arithmetic worked by hand in the comment beside
it, so a reader can check the port rather than trust it.

## Status

| function | implemented |
| --- | --- |
| `bitstream_core.lsb_first`, `.msb_first`, `.max_bits`, `.capacity` | no |
| `bitstream_core.acc_lsb`, `.acc_msb`, `.acc_bits`, `.acc_room`, `.feed` | no |
| `bitstream_core.take`, `.peek`, `.skip`, `.to_align`, `.align` | no |
| `bitstream_core.sink_lsb`, `.sink_msb`, `.sink_bits`, `.put`, `.flush` | no |
| `bitstream.order_code`, `.BitError.message` | no |
| `bitstream.reader`, `.read`, `.peek`, `.skip`, `.align` | no |
| `bitstream.bit_pos`, `.bits_left`, `.to_align` | no |
| `bitstream.writer`, `.write`, `.write_align` | no |
| `bitstream.writer_bits`, `.writer_bytes` | no |
| `bitstream.reader_acc`, `.writer_sink` | no |
