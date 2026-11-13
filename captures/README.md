# Captures (one MGD7230HW3, 2026-11-06)

| File | What |
|---|---|
| `idle-38400.sample.log` | Short idle sample, good for a first test of `tools/win_decode.py` |
| `cycle-38400-2026-11-06.raw.log` | Full Quick Dry cycle: door, start, pause/resume, option changes, cooldown, done |
| `cycle-2026-11-06.frames.tsv` | The cycle log decoded with `tools/win_decode.py` |
| `cycle-2026-11-06.markers.txt` | Time of each physical action during that cycle |
| `cycle-knob-map.markers.txt` | Knob turned through every cycle, used to map cycle ids |
| `app-writes-2026-11-06.raw.log` | Settings sent from the Whirlpool app through the stock module |
| `app-writes-2026-11-06.frames.tsv` | The app-write log decoded |
| `app-writes-2026-11-06.markers.txt` | Time of each app action |

Raw logs are ESPHome log lines filtered to the `ACU>` / `MOD>` hex dumps. `ACU` is the J25 line
(whole bus), `MOD` is J24 (stock module TX only).

Times: log timestamps are local time (UTC-6). `cycle-2026-11-06.markers.txt` is local time too;
the knob-map and app-write markers are UTC (add -6 h to line up with the logs). Markers were
typed during the capture, so they trail the bus by a few seconds.

Every frame in both decoded files passes the CRC-8 check.
