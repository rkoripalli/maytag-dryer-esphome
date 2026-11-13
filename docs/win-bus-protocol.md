# WIN bus protocol (Maytag MGD7230HW3)

Decoded from live captures on 2026-11-06 with a passive ESP32-C3 listener
(`esphome/maytag-win-sniffer.yaml`), RX-only on RIGEL pads J25 (ACU line) and J24 (module TX).
Raw logs and decoded frames are in `captures/`. Marker files give the time of each physical action;
they were typed in a chat during the capture, so they lag the bus by a few seconds.

Everything here comes from observing one dryer. Treat it as a field guide, not a spec.

## Physical layer

- **38400 baud, 8N1**, 3.3 V logic. 19200 and 57600 decode to junk.
  (The v1 config's edge-timer estimate read ~47 kBd; that is ISR latency, ignore it.)
- Multi-drop bus: every frame seen on J24 also appears on J25. J24 carries only the module's own
  frames, so it is a dedicated module-TX line.

## Framing

```
[~src]  10 02  ADDR  SEQ  LEN  PAYLOAD[LEN]  CRC8   [10 06]
```

| Field | Notes |
|---|---|
| preamble | One byte, bitwise NOT of the sender node: `FE` = node 1, `FB` = node 4, `F9` = node 6 |
| `10 02` | Start of frame |
| `ADDR` | `src << 4 \| dst`; `F` = broadcast |
| `SEQ` | Rolling counter in the high nibble, low nibble `4` (flags) |
| `LEN` | Payload length |
| `PAYLOAD` | Starts with a 2-byte API/opcode pair, e.g. `0B 23`, `0B 05`, `01 22` |
| `CRC8` | CRC-8, poly `0x31`, init `0xFF`, not reflected, xorout `0`, over `ADDR` .. end of `PAYLOAD` (400/400 frames matched) |
| `10 06` | ACK from the receiver after addressed (non-broadcast) frames |

No DLE byte-stuffing seen (no `10 10` inside payloads in these captures), but watch for it.

### Nodes

| Node | Role |
|---|---|
| 1 | ACU, main control board |
| 4 | UI / console board |
| 6 | RIGEL Wi-Fi comm module |

## Traffic map

| Frame | Rate | Meaning |
|---|---|---|
| `xF 01 22` (`1F`/`4F`/`6F`) | ~1/s each | Alive / heartbeat from each node |
| `4F 0C 23 …` / `41 0C 21` | ~1/s | UI board publishes / pings ACU (last byte is a UI state counter) |
| `41 14 21 …` | constant | UI board traffic to the ACU (counter in byte 3) |
| **`1F 0B 23` (17 B)** | ~1/s + on change | **ACU machine-status broadcast** |
| `61 0B 05` / `1F 0B 24` (13 B) | on change | Cycle settings record |
| `16 01 21 00 0B 05` | on change | ACU tells the module a key changed |
| `16 0D 22` (29 B) | every 30 s | Telemetry: IEEE-754 floats (sensor temps/ratios), not mapped yet |
| `4F 65 20` / `4F 68 20` | on key press | UI key / encoder events |
| `1F 04 2F` | on change | ACU sub-phase / output events |

## `0B 23` machine status (byte index from `0B` = 0)

| Byte | Values seen | Meaning |
|---|---|---|
| 3-4 | `0D`/`15`/`14`/`00` … | State detail / previous state (`0D` appears when Quick Dry is selected) |
| 7 | `01` idle, `02` running, `05` paused, `04` cycle complete | **Machine state**. `02` → `04` = laundry done |
| 8 | `00` / `01` | **Door**: `1` = closed, `0` = open |
| 9-10 | big-endian u16 | **Remaining time, seconds** (`0x0384` = 900 s Quick Dry; `FFFF` after the end) |
| 13 | `01` → `00` at start, `02` near the end | Phase; `02` = cooldown |
| 14 | `00` → `05` running, `01` at the end | Sub-phase |
| 15 | bit flags `80`/`B0`/`B2`/`30`/`32`/`A0` | Bit 7 clears late in the cycle (heat off?); bits 1/4/5 unknown |

No fault state was observed.

## `0B 05` cycle settings (13 B)

| Byte | Values | Meaning |
|---|---|---|
| 3 | `02` Normal, `03` Heavy Duty, `04` Whites, `05` Sanitize, `06` Towels, `07` Bulky, `09` Timed Dry, `0A` Regular, `0B` Steam Refresh, `0C` Wrinkle Control, `0D` Delicates, `0E` Quick Dry. Custom reuses the stored cycle's id; `08` not seen | Cycle id |
| 4 | `01` / `02` / `04` | Mirrors run state |
| 5 | `01` Air Only, `02` Low, `03` Medium Low (likely), `04` Medium, `05` Medium High, `06` High (not caught) | Temperature |
| 6 | `01` Less Dry, `02` Normal, `03` More Dry, `04` Very Dry (likely) | Dryness |
| 7 | `01` off, `02` on | Reduce Static |
| 8 | `01` off, `02` Wrinkle Prevent, `03` Wrinkle Prevent + steam | Wrinkle Prevent |
| 9 | `04` → `01` → `02` around Less Time | Unknown |
| 10 | `01` off, `02` on | Steam |
| 11 | one-shot: `03` drum light on, `02` drum light off, written then immediately back to `01` | Command byte |
| 12 | `01` off, `02` on | Extra Power |

The Whirlpool app's "Normal" is cycle id `0A` (the knob position labelled Regular on this console).
Turning Steam on also moved temperature to Medium and dryness to Normal in the same write burst.

## App writes through the stock module

Per change made in the Whirlpool app (~20 s cloud latency to the bus):

```
F9 10 02 61 <seq> 0D 0B 05 00 <cycle> <run> <temp> <dry> <static> <wrinkle> <b9> <steam> <b11> <power> <crc>
→ ACU ACK (10 06)
→ ACU: 16 01 21 00 0B 05        (key-changed notify)
→ module → UI board: 64 66 00 FF 00 00 02 02 03, UI answers 46 01 21 00 66 00
```

So `61 0B 05` is a **module → ACU write of the whole settings record**. The `64 66` frame to the UI
board flipped with some option changes; it may be a chime/volume setting. The damp-dry signal and
quiet mode were not located.

## Takeaways for a local integration

- The ACU broadcasts its own status, so **a lone passive listener gets everything needed for
  status**: machine state, door, time remaining, phase, cycle and options. No bus master needed.
- Laundry done = byte 7 goes `02` → `04`.
- Writes look feasible: act as node 6 (heartbeat `6F 01 22`, handle ACKs, send `61 0B 05` records,
  byte-11 pulses for the drum light). Not tested. Remote start is physically gated on the dryer
  (door closed + Remote Enable held), which the firmware strings confirm.
