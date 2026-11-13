# Stock firmware notes (static analysis)

Findings from a static, read-only look at one module's flash. The firmware itself is
Whirlpool's copyrighted code and is **not** in this repo; only facts and short identifiers
needed for interoperability are listed. Reproduce on your own dump with
`tools/rigel_flash_decode.py`.

## Image

| Partition | Type | Offset | Size |
|---|---|---|---|
| nvs | data/nvs | 0x009000 | 16K |
| otadata | data/ota | 0x00d000 | 8K |
| phy_init | data/phy | 0x00f000 | 4K |
| ota_0 | app | 0x010000 | 3072K |
| ota_1 | app | 0x310000 | 3072K |
| scratch | data | 0x610000 | 1792K |
| xs | 0x40/0x01 | 0x7d0000 | 64K |
| settings | data | 0x7e0000 | 64K |

- Dual OTA slots. Only ota_0 held data; everything past ~3 MB was `0xFF`.
- Bootloader: DIO, 40 MHz, 16 MB.
- App: project `xs_esp32`, version `OS210603-rigel-7-gea05c2d5`, built Dec 21 2022,
  esp-idf `v4.2.1-whirlpool`.
- The application is written on the **Moddable XS** JavaScript engine (`.xsb` bytecode
  resources such as `/win.xsb`, `/wmsp.xsb`, `/kvp.xsb`, `/mqtt.xsb`).

## NVS

Namespaces `FVT`, `CONFIG`, `selection`, `nimble_bond`, `WIFI`.
`CONFIG` holds model number, board part number and revision, plus the appliance and board serial
numbers. `WIFI` holds the SSID and an app-encrypted password. `selection` holds per-cycle
preference blobs. No plaintext client certificate or private key was found anywhere in flash.

## Cloud side

- Device broker host `wd.applianceconnect.net` (also `wa.applianceconnect.net`), MQTT over mutual
  TLS to AWS IoT Core. The broker host is settable at runtime (`mqttHost`, `onMqttUrlSet`).
- The server trust bundle (`/ssl/cert.xsb`) holds six public roots: Amazon Root CA 1, Starfield
  Services Root G2, DigiCert Global Root CA, DigiCert Global Root G2, DigiCert SHA2 Secure Server
  CA, USERTrust RSA. A DNS redirect to a local broker therefore cannot work without changing the
  firmware.
- Topics (device-id prefixed), binary KVP payloads:
  - `…/cmd/cc_SetKvp/fmt/binary` (writes to the appliance)
  - `…/evt/cc_Kvp/fmt/binary` (state out)
  - `…/evt/cc_SetKvpResult/fmt/binary` (write ack)
  - plus JSON admin topics (`cmd/id`, `cmd/isp`, `cmd/subscribe`, `cmd/resetcmd`, `evt/prodInfo`)
- OTA is cloud-pull of a signed and encrypted image (`*.json.signed.enc`), checked against a
  pinned key (`OTA_SPKI`). You cannot push your own image through stock OTA; a first custom
  flash must be wired.

## Bus side

Classes `Win` / `WinSerial` on a native ESP-IDF UART (GPIO27 TX, GPIO37 RX). Identifiers show
node addressing (`doNodeSetAddress`, `doGetNodes`, `onNodeFound`, nodes 0-14 in programming
logs), runtime speed negotiation (`changeSpeed`, `doBroadcastSpeedChange`), a keep-alive
(`doSendAlive`), node firmware programming (`doNodeWrite`, `doNodeErase`, `doNodeCRCRequest`)
and a built-in passive mode (`ic_enable_sniffer` / `ic_disable_sniffer`).

The live capture later settled what statics could not: 38400 8N1 and CRC-8/0x31 per frame
(see `win-bus-protocol.md`). Static string or constant scans for baud and CRC polynomials were
not usable; at 3 MB, matches are mostly coincidental.

## KVP vocabulary

The ACU (Whirlpool "Nucleus" platform) is the state source; the module bridges bus KVP to cloud
KVP. Key and enum names found as strings include:

- `MachineState` with `STATE_ACU_RUNNING`, `STATE_ACU_PAUSED`, `STATE_ACU_DELAY`,
  `STATE_ACU_FAULT`, `STATE_ACU_END`, `STATE_ACU_PROGRAMMING`, `SENSING`, `RUNNING_POST_CYCLE`
- `CycleSelect`, `CycleStatus`, `CycleSet`, `CYCLES_COMPLETED`, `Estimated_Time_Remaining`,
  `DelayTimeRemaining`, `SUB_CYCLE`, `SUB_PHASE`, `END_OF_CYCLE`
- `Door_Status`, `DoorOpen`, `DoorLocked`, `CustomerFaultCode`, `RunningHours`
- `RemoteEnable`, `RemoteEnabled`, `SmartGrid*`, `WrinkleShield`, `DampDry`, `SteamOptions`

Numeric KVP ids are not stored as a plaintext table (they resolve through the XS symbol table),
so mapping them needs a bytecode decompile or bus captures like those in `captures/`.

UI strings confirm remote start needs the door closed and Remote Enable held on the console;
remote cycle select and status reads do not.
