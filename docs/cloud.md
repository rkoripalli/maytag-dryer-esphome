# Cloud path

How the stock module talks to Whirlpool, from network observation plus public work on the
app-side API (e.g. the `whirlpool` Home Assistant integration and `bassrock/hass-whirlpool`).

- After provisioning the module holds a quiet, steady connection: about 2 KB/min up and
  0.7 KB/min down, consistent with an MQTT/TLS session with small periodic publishes.
- Device broker: `wd.applianceconnect.net` (from the firmware). The app side uses
  `wt.applianceconnect.net`, which resolves to an **AWS IoT Core ATS endpoint in us-east-2**, and
  `api.whrcloud.com` (CloudFront).
- Probing `wt.applianceconnect.net` with `openssl s_client`:

| Port | Client cert requested | Without a client cert |
|---|---|---|
| 8883 | yes | TLS 1.3, then reset |
| 443 + ALPN `x-amzn-mqtt-ca` | yes | reset |
| 443, no ALPN | no | normal HTTPS (WebSocket / SigV4 path used by the app) |

## Consequences

- The MQTT path needs mutual TLS with a per-device certificate.
- The module validates the server against public roots it ships with (see
  `firmware-notes.md`). A local broker behind a DNS redirect cannot present a certificate it
  will accept, so the trick that works for some other brands does not work here without
  modifying the firmware.
- The bus is the easier door: it is unauthenticated, the ACU self-reports, and listening needs
  no changes to the module at all.
