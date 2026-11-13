# maytag-dryer-esphome: local Maytag dryer status over the WIN bus

Reverse-engineering notes and tools for getting local, cloud-free status out of a
**Maytag MGD7230HW3** gas dryer (and probably other Whirlpool-family appliances that use the
**RIGEL** ESP32 Wi-Fi module).

The short version: the dryer's main control board (ACU) broadcasts its own state on an
internal UART bus once a second. A $5 ESP32-C3 wired **receive-only** to two pads on the Wi-Fi
module can decode it and hand Home Assistant the machine state, door, time remaining, cycle and
options, with the stock module and the Whirlpool app still working.

## What's here

| Path | What |
|---|---|
| `docs/win-bus-protocol.md` | Bus framing, CRC, node map, status and settings records, app writes |
| `docs/hardware.md` | RIGEL pinout, security state, backup/restore, sniffer wiring |
| `docs/firmware-notes.md` | Static notes on the stock firmware (partitions, cloud, KVP names) |
| `docs/cloud.md` | How the module talks to the Whirlpool cloud, and why a DNS redirect won't work |
| `esphome/maytag-win-sniffer.yaml` | ESPHome listener with decoded sensors (state, door, time, cycle, temp, dryness, wrinkle) |
| `esphome/maytag-win-capture-v1.yaml` | First capture tool: raw hex logging, switchable baud/parity, baud estimator |
| `esphome/secrets.yaml.example` | Secrets template for the configs above |
| `tools/win_decode.py` | Turn sniffer logs into a per-frame TSV with CRC checks |
| `tools/rigel_flash_decode.py` | Summarise your own module's flash dump (redacts identifying values) |
| `captures/` | Raw logs, decoded frames and action markers from one dryer (2026-11-06) |
| `examples/ha-dryer-done.yaml` | Example Home Assistant automation for "dryer done" |

## Quick start

1. Read `docs/hardware.md`, unplug the dryer, open the console and find the RIGEL module.
2. Wire a Seeed XIAO ESP32-C3: GPIO20 ← J25, GPIO21 ← J24, GND ← J30. Receive only.
3. Copy `esphome/secrets.yaml.example` to `secrets.yaml`, fill it in, and flash
   `esphome/maytag-win-sniffer.yaml`.
4. Power the XIAO from a battery bank or isolated charger, close up, plug the dryer back in.
5. Watch `Dryer state` go `Running` → `Complete`.

To check your own captures: `python tools/win_decode.py my-log.txt > frames.tsv`.

## Status

- Read-only status: **working** on one MGD7230HW3.
- Writes (cycle settings, drum light) are decoded from app traffic but **not tested** from the
  sniffer. Remote start stays gated by the dryer's physical Remote Enable button.
- Not mapped yet: the 30-second float telemetry frame, fault states, a few option bytes.

Captures and corrections from other models are welcome.

## Not included, on purpose

No firmware images, flash dumps, certificates, keys, Wi-Fi credentials or serial numbers.
The stock firmware is Whirlpool's code; read your own module if you need it.

## Disclaimer

Not affiliated with or endorsed by Whirlpool Corporation. Maytag and Whirlpool are trademarks
of their owners. Opening an appliance can void its warranty and involves mains voltage and,
on gas models, gas. You do this at your own risk.

## License

MIT, see `LICENSE`.
