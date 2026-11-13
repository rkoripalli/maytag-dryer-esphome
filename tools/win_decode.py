#!/usr/bin/env python3
"""Parse a WIN-bus sniffer log into frames (TSV).

Input: ESPHome log lines from esphome/maytag-win-sniffer.yaml or
esphome/maytag-win-capture-v1.yaml, i.e. lines containing "ACU>" or "MOD>" followed by
hex bytes (dot- or space-separated).

Frame layout (see docs/win-bus-protocol.md):

    [~src] 10 02 | ADDR | SEQ | LEN | PAYLOAD[LEN] | CRC8 | [10 06 ack]

CRC-8: poly 0x31, init 0xFF, not reflected, xorout 0, over ADDR..end of PAYLOAD.

Output, one line per record:
    time  dir  ADDR  SEQ  LEN  payload-hex  crc  ok|BAD
Bytes between frames (preamble bytes FB/FE/F9 and 10 06 ACKs) are printed as "gap" records.

usage: python win_decode.py <capture.log> > frames.tsv
"""
import re
import sys

STX = b"\x10\x02"
LINE = re.compile(
    r"^\[(\d\d:\d\d:\d\d\.\d+)\].*?(ACU>|MOD>)(?:[^\]]*\]:)?\s*([0-9A-Fa-f]{2}(?:[. ][0-9A-Fa-f]{2})*)"
)
ANSI = re.compile(r"\\033\[[0-9;]*m|\x1b\[[0-9;]*m")


def crc8(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = ANSI.sub("", raw).replace("]\\[", "] [")
            m = LINE.search(raw)
            if m:
                hexstr = re.sub(r"[. ]", "", m.group(3))
                yield m.group(1), m.group(2)[:3], bytes.fromhex(hexstr)


def frames(path):
    """Length-based framing. Yields (time, dir, kind, bytes)."""
    bufs = {"ACU": bytearray(), "MOD": bytearray()}
    times = {"ACU": None, "MOD": None}
    for t, d, data in lines(path):
        buf = bufs[d]
        if not buf:
            times[d] = t
        buf += data
        while True:
            s = buf.find(STX)
            if s < 0 or len(buf) < s + 5:
                break
            if s:
                yield times[d], d, "gap", bytes(buf[:s])
            n = buf[s + 4]
            need = s + 5 + n + 1
            if len(buf) < need:
                del buf[:s]
                break
            yield times[d], d, "frame", bytes(buf[s + 2:need])
            del buf[:need]
            times[d] = t


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    for t, d, kind, b in frames(argv[1]):
        if kind == "gap":
            print(f"{t}\t{d}\tgap\t{b.hex(' ')}")
            continue
        addr, seq, n = b[0], b[1], b[2]
        body, crc = b[:3 + n], b[3 + n]
        ok = "ok" if crc8(body) == crc else "BAD"
        print(f"{t}\t{d}\t{addr:02X}\t{seq:02X}\t{n}\t{b[3:3 + n].hex(' ')}\t{crc:02x}\t{ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
