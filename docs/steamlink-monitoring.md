# Monitoring Steam Link / Remote Play

Steam writes a surprisingly complete diagnostic log for every streaming session.
[`scripts/steamlink-exporter.py`](../scripts/steamlink-exporter.py) turns it into
Prometheus metrics, so the question "why is my stream stuttering?" becomes a
graph instead of an evening of guessing.

Run it on the **streaming host** — the machine running Steam — not the client.

## What you get

| metric | meaning |
|---|---|
| `steamlink_streaming_active` | 1 while a stream is live |
| `steamlink_relayed{route}` | 1 if routed via a Steam Datagram Relay instead of peer-to-peer |
| `steamlink_rtt_seconds` | round-trip time to the client |
| `steamlink_throughput_bytes_per_second{direction}` | actual stream throughput |
| `steamlink_target_throughput_bytes_per_second{kind}` | what Steam is *aiming* for |
| `steamlink_quality_ratio{direction}` | Steam's connection-quality figure, 0–1 |
| `steamlink_frame_stage_seconds{stage}` | frame time split: game, capture, convert, encode, network, decode, display |
| `steamlink_slow_frames_total{blame}` | slow-frame events, by the stage Steam blamed |
| `steamlink_client_connections_total{client,path}` | connections per client, `direct` vs `indirect` |
| `steamlink_client_connected{client,path}` | the client currently connected |

All in Prometheus base units (seconds, bytes) and clean under
`promtool check metrics`. Steam logs kbit/s and milliseconds; the exporter
converts.

The three that earn their keep:

- **`relayed`** — the single most useful number. See below.
- **`frame_stage_seconds`** — tells you *which machine* to fix. High `network`
  means the link; high `encode` means the host; high `decode` means the client.
- **throughput vs target** — actual well below target means the path can't
  carry what Steam is asking for.

## Why a textfile collector

The exporter writes a `.prom` file that `node_exporter` serves. No new daemon,
no new port, no container — and your streaming host is probably already scraped.

```bash
sudo install -m 0755 steamlink-exporter.py /usr/local/bin/
sudo install -d -m 0755 /var/lib/node_exporter/textfile
```

Enable the collector (Arch/CachyOS reads `/etc/conf.d/prometheus-node-exporter`):

```bash
NODE_EXPORTER_ARGS="--collector.textfile.directory=/var/lib/node_exporter/textfile"
```

Run it every 15 seconds:

```ini
# /etc/systemd/system/steamlink-exporter.service
[Service]
Type=oneshot
Environment=STEAM_LOGS=/home/<you>/.local/share/Steam/logs
Environment=TEXTFILE_DIR=/var/lib/node_exporter/textfile
ExecStart=/usr/bin/python3 /usr/local/bin/steamlink-exporter.py
Nice=10
```

```ini
# /etc/systemd/system/steamlink-exporter.timer
[Timer]
OnBootSec=30s
OnUnitActiveSec=15s
AccuracySec=1s

[Install]
WantedBy=timers.target
```

!!! warning "Set `STEAM_LOGS` explicitly"
    The script defaults to `~/.local/share/Steam/logs`. As a system service it
    runs as root, where `~` is `/root` — so without `STEAM_LOGS` it finds
    nothing and quietly reports an idle host.

Confirm it's being served:

```bash
curl -s localhost:9100/metrics | grep -E '^steamlink_|node_textfile_scrape_error'
```

## Design decisions worth knowing

**Stale values are suppressed, not frozen.** A naive parser reports the last
ping it ever saw, so an idle host shows a confident 18 ms forever. This one
checks each line's own timestamp and only reports live values if they are
younger than `STALE_SECONDS` (default 90). Otherwise it reports
`streaming_active 0` and omits the live gauges.

It uses the **line timestamp**, not the file's mtime — copying or touching the
log won't fool it into looking live.

**Atomic writes.** It writes to a temp file and renames it, so `node_exporter`
never serves a half-written file.

**Counters reset when Steam truncates its log.** That's fine: `rate()` and
`increase()` handle counter resets.

## The relay problem, as a metric

If `steamlink_relayed` is 1, Steam could not establish a direct connection and
fell back to its Datagram Relay. The log shows it as a route like:

```
Connected SDR->lhr->lhr  Ping: 16ms  ...  qual 100.0%
```

The trap: ping is fine and quality reads 100%, so it looks healthy. But the
per-frame `network` stage sits at 30–50 ms, which caps you well below 60 fps no
matter how fast the host is.

The usual cause on a pf-based firewall (OPNsense, pfSense) is **port-rewriting
outbound NAT**, which behaves as symmetric NAT and defeats UDP hole punching.
You can see it in the state table — the same internal port mapped to a
different external port per destination:

```
<wan>:6211   (<host>:43826) -> <dest-a>
<wan>:48167  (<host>:49182) -> <dest-b>
```

Fix: an outbound NAT rule with **static port** enabled, scoped to the streaming
host and UDP. It opens no inbound ports — inbound policy is unchanged — it just
makes that host's NAT endpoint-independent. Pin the host with a DHCP
reservation first, or the rule silently points at nothing when its lease moves.

UPnP/NAT-PMP also fixes it, but lets any LAN device open real inbound forwards.
Static port is the more conservative choice.

## Parser coverage

Verified against a real host log: 1650/1650 connection lines and 6/6
slow-frame lines matched, including the variant where Steam writes
`qual ???%%` for an unmeasured direction.
