#!/usr/bin/env python3
"""Static, read-only decode of a Whirlpool RIGEL (ESP32) flash dump.

Bring your own dump: this repo ships no firmware. Read your module's flash with esptool
(see docs/hardware.md), then run:

    python rigel_flash_decode.py rigel_16MB.bin > report.md

What it prints (Markdown):
  1. Partition table, bootloader header, esp_app_desc_t of ota_0.
  2. NVS key/value listing. Values of anything that identifies the unit or the owner
     (serial numbers, Wi-Fi SSID/password, keys, certs, BLE bonds) are REDACTED and shown
     only as key name + flash offset.
  3. A keyword-filtered string survey of the ota_0 app (cloud hosts, MQTT topics, KVP names,
     WIN/WMSP identifiers, OTA identifiers).

Nothing is ever written next to the dump. Pass --secrets-dir DIR only if you want the
redacted NVS values written as files for your own use; keep that folder private.
"""
import argparse
import binascii
import os
import re
import struct
import sys

PART_TYPE = {0: "app", 1: "data"}
PART_SUB = {
    (0, 0x00): "factory", (0, 0x10): "ota_0", (0, 0x11): "ota_1", (0, 0x20): "test",
    (1, 0x00): "ota(otadata)", (1, 0x01): "phy", (1, 0x02): "nvs", (1, 0x03): "coredump",
    (1, 0x04): "nvs_keys", (1, 0x05): "efuse", (1, 0x06): "undefined",
    (1, 0x80): "esphttpd", (1, 0x81): "fat", (1, 0x82): "spiffs", (1, 0x83): "littlefs",
}
NVS_TYPES = {0x01: "u8", 0x11: "i8", 0x02: "u16", 0x12: "i16", 0x04: "u32", 0x14: "i32",
             0x08: "u64", 0x18: "i64", 0x21: "str", 0x41: "blob", 0x42: "blob_data", 0x48: "blob_idx"}
INT_FMT = {"u8": "<B", "i8": "<b", "u16": "<H", "i16": "<h", "u32": "<I", "i32": "<i",
           "u64": "<Q", "i64": "<q"}
SECRET_HINTS = ("pass", "psk", "passwd", "key", "secret", "priv", "said", "cert", "ble", "pin",
                "token", "cred", "seed", "serial", "ssid", "mac", "bond", "id")
SAFE_KEYS = {"modelnumber", "brdpartnumb", "brdrevision"}
SECRET_NAMESPACES = {"WIFI", "nimble_bond", "nvs.net80211"}
STR_RE = re.compile(rb"[\x20-\x7e]{4,}")

SURVEYS = [
    ("Cloud hosts / URLs / MQTT", ["applianceconnect", "http://", "https://", "mqtt", "broker",
                                    "amazonaws", "iot-2"]),
    ("MQTT topic fragments", ["/cmd/", "/evt/", "cc_", "/fmt/", "setkvp"]),
    ("KVP / machine-state names", ["machinestate", "cyclestatus", "cycleselect", "door_status",
                                    "dooropen", "cycles_completed", "estimated_time",
                                    "end_of_cycle", "sub_cycle", "remoteenable", "smartgrid",
                                    "system_state", "state_acu", "customerfault", "kvp"]),
    ("WIN / WMSP / SAP identifiers", ["wmsp", "/win.xsb", "winserial", "changespeed",
                                       "broadcastspeed", "sendalive", "crc16", "crc32",
                                       "sniffer", "binarymessage", "doNode"]),
    ("OTA identifiers", ["ota", "softwareupdate", "otadecrypt", "ota_spki", "signed.enc"]),
]


def out(s=""):
    sys.stdout.write(s + "\n")


def is_secret(ns, key):
    if ns in SECRET_NAMESPACES:
        return True
    k = key.lower()
    if k in SAFE_KEYS:
        return False
    return any(h in k for h in SECRET_HINTS)


def partitions(data):
    parts = []
    base = 0x8000
    for i in range(0, 0x1000, 32):
        e = data[base + i:base + i + 32]
        if e[:2] == b"\xaa\x50":
            t, s = e[2], e[3]
            off, sz = struct.unpack("<II", e[4:12])
            name = e[12:28].split(b"\x00")[0].decode("ascii", "replace")
            parts.append((name, t, s, off, sz))
        elif e[:2] == b"\xeb\xeb" or e[:2] == b"\xff\xff":
            break
    return parts


def report_partitions(data, parts):
    out("## 1. Partition table (@ 0x8000)")
    out()
    out("| name | type | subtype | offset | size |")
    out("|------|------|---------|--------|------|")
    for name, t, s, off, sz in parts:
        out(f"| {name} | {PART_TYPE.get(t, hex(t))} | {PART_SUB.get((t, s), hex(s))} "
            f"| 0x{off:06x} | 0x{sz:x} ({sz // 1024}K) |")
    names = {p[0] for p in parts}
    out()
    out(f"Dual OTA slots (ota_0 + ota_1): **{'yes' if {'ota_0', 'ota_1'} <= names else 'no'}**")
    out()
    bl = data[0x1000:0x1000 + 4]
    out("### Bootloader header (@ 0x1000)")
    if bl[0] == 0xE9:
        mode = {0: "QIO", 1: "QOUT", 2: "DIO", 3: "DOUT"}.get(bl[2], hex(bl[2]))
        freq = {0: "40MHz", 1: "26MHz", 2: "20MHz", 0xF: "80MHz"}.get(bl[3] & 0xF, hex(bl[3] & 0xF))
        size = {0: "1MB", 1: "2MB", 2: "4MB", 3: "8MB", 4: "16MB"}.get(bl[3] >> 4, hex(bl[3] >> 4))
        out(f"- segments {bl[1]}, flash mode {mode}, freq {freq}, size {size}")
    else:
        out(f"- unexpected magic 0x{bl[0]:02x}")
    out()
    ota0 = next((p for p in parts if p[0] == "ota_0"), None)
    if ota0:
        a = ota0[3]
        if struct.unpack("<I", data[a + 0x20:a + 0x24])[0] == 0xABCD5432:
            def cstr(lo, hi):
                return data[a + lo:a + hi].split(b"\x00")[0].decode("ascii", "replace")
            out("### App descriptor (ota_0)")
            out(f"- project `{cstr(0x50, 0x70)}`, version `{cstr(0x30, 0x50)}`")
            out(f"- built {cstr(0x70, 0x80)} {cstr(0x80, 0x90)}, esp-idf `{cstr(0x90, 0xB0)}`")
            out()


def report_nvs(data, parts, secrets_dir):
    nvs = next((p for p in parts if p[1] == 1 and p[2] == 2), None)
    out("## 2. NVS (live entries)")
    out()
    if not nvs:
        out("No NVS partition found.")
        return
    noff, nsz = nvs[3], nvs[4]
    blob = data[noff:noff + nsz]
    live, order = {}, []
    for pstart in range(0, len(blob), 4096):
        page = blob[pstart:pstart + 4096]
        if len(page) < 64 or struct.unpack("<I", page[0:4])[0] == 0xFFFFFFFF:
            continue
        bitmap = page[32:64]
        slot = 0
        while slot < 126:
            st = (bitmap[slot // 4] >> ((slot % 4) * 2)) & 0b11
            if st == 0b11:
                break
            ent = page[64 + slot * 32:64 + slot * 32 + 32]
            ns_i, typ, span, chunk = ent[0], ent[1], max(ent[2], 1), ent[3]
            if st != 0b10:
                slot += 1
                continue
            key = ent[8:24].split(b"\x00")[0].decode("ascii", "replace")
            tn = NVS_TYPES.get(typ)
            val = raw = None
            if tn in INT_FMT:
                val = struct.unpack(INT_FMT[tn], ent[24:24 + struct.calcsize(INT_FMT[tn])])[0]
            elif tn in ("str", "blob", "blob_data"):
                dlen = struct.unpack("<H", ent[24:26])[0]
                raw = page[64 + (slot + 1) * 32:64 + (slot + 1) * 32 + dlen]
                if tn == "str":
                    val = raw.split(b"\x00")[0].decode("utf-8", "replace")
            elif tn == "blob_idx":
                val = f"<blob idx, {struct.unpack('<I', ent[24:28])[0]} B>"
            if tn:
                k3 = (ns_i, key, chunk)
                if k3 not in live:
                    order.append(k3)
                live[k3] = (ns_i, key, tn, val, raw, noff + pstart + 64 + slot * 32)
            slot += span
    ns_names = {v[3]: v[1] for v in live.values() if v[0] == 0 and v[2] == "u8"}
    out("Namespaces: " + ", ".join(f"`{v}`" for _, v in sorted(ns_names.items())))
    out()
    out("| ns | key | type | value |")
    out("|----|-----|------|-------|")
    n_secret = 0
    for k3 in order:
        ns_i, key, tn, val, raw, off = live[k3]
        if ns_i == 0:
            continue
        ns = ns_names.get(ns_i, f"#{ns_i}")
        if is_secret(ns, key):
            n_secret += 1
            out(f"| {ns} | `{key}` | {tn} | [redacted, offset 0x{off:x}] |")
            if secrets_dir:
                payload = raw if raw is not None else str(val).encode()
                with open(os.path.join(secrets_dir, f"nvs_{ns}_{key}_{k3[2]}.bin"), "wb") as fh:
                    fh.write(payload)
            continue
        if raw is not None and tn != "str":
            val = f"blob {len(raw)} B: {binascii.hexlify(raw[:24]).decode()}" + ("..." if len(raw) > 24 else "")
        out(f"| {ns} | `{key}` | {tn} | {val} |")
    out()
    out(f"{n_secret} entr{'y' if n_secret == 1 else 'ies'} redacted"
        + (f", written to `{secrets_dir}`." if secrets_dir else "."))
    out()


def report_strings(data, parts):
    ota0 = next((p for p in parts if p[0] == "ota_0"), None)
    if not ota0:
        return
    lo, hi = ota0[3], ota0[3] + ota0[4]
    strings = sorted({m.group().decode("ascii") for m in STR_RE.finditer(data[lo:hi])})
    out(f"## 3. String survey of ota_0 ({len(strings)} printable strings >= 4 chars)")
    out()
    for title, pats in SURVEYS:
        pl = [p.lower() for p in pats]
        hits = [s for s in strings if any(p in s.lower() for p in pl)]
        out(f"### {title} ({len(hits)})")
        for s in hits:
            out(f"- `{s.replace('`', chr(39))}`")
        out()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", help="raw flash image read with esptool read_flash")
    ap.add_argument("--secrets-dir", help="write redacted NVS values here (keep private)")
    ap.add_argument("--no-strings", action="store_true", help="skip the string survey")
    args = ap.parse_args()
    with open(args.dump, "rb") as fh:
        data = fh.read()
    if args.secrets_dir:
        os.makedirs(args.secrets_dir, exist_ok=True)
    out(f"# RIGEL flash decode: {os.path.basename(args.dump)} ({len(data)} bytes)")
    out()
    parts = partitions(data)
    report_partitions(data, parts)
    report_nvs(data, parts, args.secrets_dir)
    if not args.no_strings:
        report_strings(data, parts)


if __name__ == "__main__":
    main()
