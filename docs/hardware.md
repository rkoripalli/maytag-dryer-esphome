# Hardware: the RIGEL Wi-Fi module

> **Safety first.** The dryer runs on mains (and gas, for the MGD models). Unplug it before
> opening the console. Never connect a PC-powered USB adapter to the module while the dryer is
> live; power a sniffer from a battery bank or an isolated charger. You do this at your own risk.

## Where it is

The Wi-Fi module sits in the console. Remove the console's rear screws and tilt the console to
reach it. Whirlpool's own service docs describe the module as a common design across product
lines that talks to the appliance over Whirlpool's internal bus (WIN/WIDE) and to the internet
over Wi-Fi.

## The module

- FCC ID **2AC7Z-RIGEL**, registered to Espressif; datasheet title "RIGEL ... W11261889".
- ESP32-D0WD-V3 + SPI NOR flash + 40 MHz crystal on a 40-pad castellated edge module.
- The FCC photos (REV B) show an 8 MB GD25Q64. The unit studied here carried a **16 MB
  GD25Q128** (JEDEC `0xC84018`), so read the flash ID before assuming a size.

### Pinout (RIGEL REV C datasheet)

| Pad | Name | Use |
|---|---|---|
| J2, J31 | VDD33 | 3.3 V |
| J1, J15, J30, J32-34, J40 | VSS | GND |
| J24 | WIN TX (GPIO27) | module → bus |
| J25 | WIN RX (GPIO37) | bus → module (ACU line) |
| J26 | GPIO0 / Boot | pull low at reset for download mode |
| J27 | UART0_RX | ← adapter TX |
| J28 | UART0_TX | → adapter RX |
| J29 | EN | chip enable; pulse low to reset |
| J3-J5 | | class-B micro wake/int |
| J6-J9 | | JTAG (MTMS/MTDI/MTCK/MTDO) |
| J10-J12 | | I2S audio |
| J16-J23 | | display SPI |
| J35-J39 | | NC |

## Security state (as found)

Read from eFuses on one unit; check your own with `espefuse summary` (read-only).

- Flash encryption **off** (`FLASH_CRYPT_CNT = 0`), Secure Boot **off** (`ABS_DONE_0/1 = 0`).
- UART download mode enabled, JTAG enabled, no read/write protect.

So the flash reads in plaintext and a modified image would boot.

**Never burn eFuses** (`espefuse burn*`). One burned `FLASH_CRYPT_CNT` or `ABS_DONE` bit is
permanent and removes the restore path described below.

## Reading the flash (backup)

With the dryer unplugged, power the module from the USB-UART adapter's 3.3 V and wire
J27 ← TX, J28 → RX, GND, J26 (GPIO0) low at reset, J29 (EN) to the adapter's reset line.

```
python -m esptool --chip esp32 -p <PORT> --baud 115200 flash_id
python -m esptool --chip esp32 -p <PORT> --baud 115200 read_flash 0 0x1000000 rigel_16MB.bin
```

Long single-pass reads may fail esptool's end-of-read digest on a marginal link. Reading in
1 MB chunks (each verified) worked reliably.

Keep the dump private. It holds your Wi-Fi credentials, the unit's serial numbers and
Whirlpool's firmware. `tools/rigel_flash_decode.py` summarises a dump and redacts the
identifying NVS values by default.

## Restore

Because nothing is locked, writing the original dump back always returns the module to stock:

```
python -m esptool --chip esp32 -p <PORT> --baud 115200 write_flash 0x0 rigel_16MB.bin
```

## Passive sniffer wiring (Seeed XIAO ESP32-C3)

| XIAO | Module pad |
|---|---|
| D7 / GPIO20 (RX) | J25 (ACU line) |
| D6 / GPIO21 (RX) | J24 (module TX) |
| GND | J30 |

Receive-only; the stock module keeps working. See `esphome/`.

### For future writes (not done yet)

1. XIAO TX → 1 kΩ → J24.
2. A switch from J29 (EN) to GND: closed holds the stock module in reset so the XIAO owns J24.
3. A UART pigtail (J26, J27, J28, J29, J30) for reflashing without opening the console again.
