# bitstream-nv

Many formats store values that are not a whole number of bytes: a
three-bit block header, a five-bit pixel, a Huffman code of any length
from one to fifteen. Reading them means reading bits rather than bytes.
This package reads and writes 1 to 64 bits at a time over bytes the
caller already holds, in both of the bit orders that real formats use.

**Status: NOT IMPLEMENTED — interface only.** Every function is declared
with its full signature, but every body is a `todo()` that panics when
called. The package is published so its design can be reviewed and
depended on before it is implemented. Version 0.1.0 will be the first
working release.

## What a bit stream is

A bit stream is a run of bytes read as one long sequence of bits. A
reader keeps an **accumulator**: an integer holding the bits pulled out
of the source but not yet handed to the caller, and a count of how many
of them are live. A read of `n` bits takes them off the accumulator, and
the accumulator is refilled a byte at a time.

The **bit order** says which end of each byte the first bit comes from.
**LSB-first** takes the least significant bit of the byte first.
**MSB-first** takes the most significant bit first. A stream is one
order from end to end, and both orders are in wide use.

A stream read in the wrong order does not fail. It answers plausible
numbers, because every bit pattern is a legal reading of some value.
This is the fact a reader of this package most often came for, so it is
a table.

| Format | Order | Where it says so |
| --- | --- | --- |
| DEFLATE, zlib and gzip, other than the Huffman codes | LSB-first | RFC 1951 section 3.1.1 |
| DEFLATE's Huffman codes, inside that same stream | MSB-first | RFC 1951 section 3.1.1 |
| JPEG entropy-coded segments | MSB-first | ITU-T T.81 section F.1.2.1 |
| PNG pixel rows of 1, 2 or 4 bits | MSB-first | RFC 2083 section 7.2 |
| Brotli | LSB-first | RFC 7932 section 1.2 |
| LZMA and the xz range coder | MSB-first | the xz format specification section 4 |
| Protocol field diagrams drawn left to right | MSB-first | every RFC that draws one |

DEFLATE appears twice, and that is what RFC 1951 section 3.1.1 says.
Data elements are packed starting at the least significant bit, and
Huffman codes are packed starting at the most significant bit of the
code, in one stream. An inflater reads the header, the lengths and the
extra bits LSB-first. It reads each code LSB-first as well and reverses
it, because reversing a code of at most fifteen bits costs less than
running two accumulators.

**Alignment** is the third idea. Some formats resume on a byte boundary
after a header, so a reader must be able to discard the bits up to the
next boundary. DEFLATE's stored block does this.

| Quantity | Value |
| --- | --- |
| Bits one read or write may ask for | 1 to 64 |
| Bits the accumulator holds | 64 |
| Bits of room one refill needs | 8 |
| Bits a writer holds back between writes | 0 to 7 |
| Whole bytes one write can complete | 0 to 8 |
| Bits discarded by an alignment | 0 to 7 |

## Install

```
novo pkg add bitstream-nv
```

## Example

Every DEFLATE stream opens with a one-bit final flag and a two-bit block
type, both LSB-first, as RFC 1951 section 3.2.3 describes.

```novo
use std.bytes
use bitstream

fn main() [io]
    // A reader over two bytes, LSB-first, positioned at bit zero.
    let r = bitstream.reader(bytes.from_hex("0300") ?? bytes.zeros(0), BitsLsbFirst)

    // BFINAL: one bit, 1 when this is the last block of the stream.
    match bitstream.read(r, 1)
        Err(e)   => println(e.message())
        Ok(last) =>
            // BTYPE: two bits, 1 for a block with the fixed Huffman
            // tables. The reader from the previous read carries the
            // position forward.
            match bitstream.read(last.reader, 2)
                Err(e)   => println(e.message())
                Ok(kind) => println("final=${last.value} type=${kind.value}")
```

Build and test with `novo pkg build` and `novo test`. Today `novo test`
fails on purpose: every test reaches a `not implemented: bitstream.<fn>`
panic. The tests are the specification the implementation will have to
satisfy.

## What the package contains

| Module | Contents |
| --- | --- |
| `bitstream_core` | The accumulator and its mirror the sink: two integers and an order each, with take, peek, skip, align, put and flush. It holds no buffer and allocates nothing. |
| `bitstream` | A reader over a `Bytes` and a writer that collects finished bytes, with the bit order as an enum, the three named refusals, and the position and remaining counts. |

## How to choose an entry point

**`bitstream.reader` and `bitstream.writer` are for a caller holding the
whole payload.** They refill and drain the accumulator for you, and they
answer a `Result` on a bad call.

**`bitstream_core.acc_lsb` and `acc_msb` are for a caller who owns the
bytes.** You feed the accumulator a byte at a time and check
`acc_room` before each refill. Nothing is allocated, so this is the form
a device and an interrupt handler use.

**`bitstream.reader_acc` and `bitstream.writer_sink` cross between
them.** They answer the plain accumulator and sink inside a host reader
or writer. A program that parses a header on a host and runs the inner
loop on a device needs those two calls.

## The rules a user needs

1. **The bit order is chosen once, at the constructor, and never
   changes.** It is a field of the value rather than a choice per call.
   A stream is one order from end to end, and the table above says which
   order each format uses.
2. **A value arrives right-aligned in both orders.** A read of 3 answers
   0 to 7 whichever way the stream is packed, so the caller's arithmetic
   does not change with the format.
3. **A read of 64 bits whose top bit is set answers a negative number.**
   The value travels in an `Int`, which is signed and 64 bits wide, and
   that is the bit pattern. A caller who wants the unsigned reading
   reads 32 bits and 32 bits and combines them.
4. **A width outside 1 to 64 is refused.** That is
   `BitsWidthOutOfRange`. Zero bits is not a read: a caller who means
   nothing writes no call.
5. **A read past the end is refused and moves nothing.**
   `BitsExhausted(at, need)` gives the bit offset and the width asked
   for. The reader comes back unchanged, so a speculative parse costs
   nothing to abandon.
6. **A value with a bit set above its field is refused, not masked.**
   That is `BitsValueTooWide`. A masked value writes a document that
   decodes to a different number.
7. **Every position is counted in bits.** `bit_pos`, `bits_left` and
   `to_align` are all bit counts, because a bit stream has no other
   landmark. A caller wanting a byte offset divides by eight.
8. **`bitstream_core` answers a flag, not a `Result`.** `BitTake.ok` and
   `BitEmit.ok` are false for a call that did not happen, and the value
   comes back unchanged. A `@value` struct cannot be a `Result` payload,
   and a reader that allocated at each refill boundary would allocate
   once per byte of a compressed stream.
9. **`bitstream_core.feed` needs eight bits of room.** Check
   `acc_room` first. A byte fed with less room is dropped and the
   accumulator comes back unchanged.
10. **Alignment discards bits and pads with zeros.** `align` drops up to
    seven bits and never fails. `write_align` and
    `bitstream_core.flush` pad the partial byte with zero bits. A format
    that pads with ones writes them itself first.
11. **A Huffman decoder peeks and then skips.** Peek the longest code
    the table holds, look the prefix up, then skip exactly the length
    the table gives. A bit stream has no way to put bits back.

## Running on a microcontroller

novo-lang lets a package state which of its modules can run on a device
with no heap allocator, and the compiler checks that claim on every
build. Here the claim covers `bitstream_core` and nothing else. It takes
and answers `Int` and `u8`, and it holds no buffer.

`tests/embedded_probe.nv` is that claim as a program that either builds
or does not. It builds today:

```bash
novo build --target=nrf52-qemu tests/embedded_probe.nv
```

The probe produces a Cortex-M4 executable that fills an accumulator,
takes, peeks, skips and aligns, then writes fields back through the
sink. It builds and it is not run: every function it calls is a `todo()`
today.

**A device cannot use the `bitstream` module.** That module speaks
`Bytes`, and the embedded runtime defines none of the byte-buffer
symbols. One host-only function anywhere in a compilation unit is an
undefined symbol at link time on a device, whether or not the firmware
calls it. That is why the package is two modules.

## What is not included

- **Any check on the data.** A bit stream carries no framing, no tags
  and no checksums, so there is nothing in the bytes to find wrong. All
  three refusals are caller faults, and a truncated stream reaches the
  caller as a read asking for more bits than were supplied.
- **A read wider than 64 bits.** The value travels in one `Int`. A
  caller reading a wider field reads it in pieces.
- **An unsigned 64-bit read.** See rule 3.
- **Input and output.** The reader takes bytes the caller already holds,
  and the writer answers bytes for the caller to write somewhere. No
  function here declares an effect.
- **Huffman tables, and the code reversal a DEFLATE decoder needs.**
  Those belong to the codec that owns the table.
- **A growable `Bytes` writer in the core half.** `BitWriter` collects
  its output in a list, which a device cannot allocate. Firmware writes
  through `bitstream_core.put`, which emits into an inline array of
  eight bytes.

## Related packages

- [flate-nv](https://novo-lang.org/packages/flate-nv) is DEFLATE, zlib
  and gzip. It is the largest consumer of a bit reader, and the LSB-first
  order in the table above is its order.
- [brotli-nv](https://novo-lang.org/packages/brotli-nv) and
  [zstd-nv](https://novo-lang.org/packages/zstd-nv) are the other
  compression formats with sub-byte fields.
- [png-nv](https://novo-lang.org/packages/png-nv) unpacks pixel rows of
  1, 2 and 4 bits, which is an MSB-first read of a fixed width.
- [leb128-nv](https://novo-lang.org/packages/leb128-nv) and
  [varint-nv](https://novo-lang.org/packages/varint-nv) encode integers
  in a variable number of whole bytes, which needs no bit reader.
- [base64-nv](https://novo-lang.org/packages/base64-nv) reads six bits
  at a time out of a fixed twenty-four-bit group, and does its own
  shifting for that one width.

## Tests

```bash
novo test tests/bitstream_tests.nv      # 21 tests
```

The vectors are bytes from the format specifications in the table above,
with the arithmetic worked out by hand in a comment beside each one. The
surface follows `bitvec` in Rust and `bitstring` in Python.

The suite asserts that the two orders answer different numbers from the
same byte, that a DEFLATE block header reads as RFC 1951 writes it, that
a stored block aligns after its header, that peek does not consume and
skip does, that the counts are in bits, that a read past the end is
refused and moves nothing, that a width outside 1 to 64 is refused, that
a writer completes a byte only when it has eight bits, that a partial
byte is padded with zeros, that a value wider than its field is refused
rather than masked, that an MSB-first write puts a field diagram down
left to right, and that a host reader and writer hand their state to the
device half unchanged.

The tests compile today and fail at run, each on the `not implemented`
panic that is its body. That is the expected state of an interface
release. They turn green one at a time as bodies land.

## Implementation status

| Item | Implemented |
| --- | --- |
| `bitstream_core.lsb_first`, `.msb_first`, `.max_bits`, `.capacity` | no |
| `bitstream_core.acc_lsb`, `.acc_msb`, `.acc_bits`, `.acc_room`, `.feed` | no |
| `bitstream_core.take`, `.peek`, `.skip`, `.to_align`, `.align` | no |
| `bitstream_core.sink_lsb`, `.sink_msb`, `.sink_bits`, `.put`, `.flush` | no |
| `bitstream.order_code`, `BitError.message` | no |
| `bitstream.reader`, `.read`, `.peek`, `.skip`, `.align` | no |
| `bitstream.bit_pos`, `.bits_left`, `.to_align` | no |
| `bitstream.writer`, `.write`, `.write_align` | no |
| `bitstream.writer_bits`, `.writer_bytes` | no |
| `bitstream.reader_acc`, `.writer_sink` | no |

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
