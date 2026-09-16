#!/usr/bin/env python3
"""Steam Remote Play / Steam Link metrics for node_exporter's textfile collector.

Parses Steam's own streaming logs and writes Prometheus metrics atomically.
Run on the streaming HOST (the machine running Steam), not the client.

Why a textfile collector and not a daemon: no new port, no new container, and
node_exporter is already scraped - so nothing new to secure or template.
"""
import os, re, time, datetime, glob, tempfile, collections

STEAM = os.environ.get("STEAM_LOGS", os.path.expanduser("~/.local/share/Steam/logs"))
OUT   = os.environ.get("TEXTFILE_DIR", "/var/lib/node_exporter/textfile")
# live values are only trusted if the log line is at least this recent
STALE = int(os.environ.get("STALE_SECONDS", "90"))

SLOW = re.compile(
    r'^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\].*Slow framerate: '
    r'game (?P<game>[\d.]+), capture (?P<capture>[\d.]+), convert (?P<convert>[\d.]+), '
    r'encode (?P<encode>[\d.]+), network (?P<network>[\d.]+), '
    r'decode (?P<decode>[\d.]+), display (?P<display>[\d.]+) \((?P<blame>\w+)\)')
NET = re.compile(
    r'^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\].*SteamNetworkingSockets connection: '
    r'Connected (?P<route>\S+)\s+Ping: (?P<ping>\d+)ms '
    r'IN: (?P<in_kbit>[\d.]+)kbit (?P<in_pps>[\d.]+) pkt/s qual (?P<in_q>[\d.?]+)%?%? '
    r'OUT: (?P<out_kbit>[\d.]+)kbit (?P<out_pps>[\d.]+) pkt/s qual (?P<out_q>[\d.?]+)')
TARGET = re.compile(r'Setting target bitrate to (?P<t>\d+) Kbit/s, burst bitrate is (?P<b>\d+)')
CONN = re.compile(r'^\[(?P<ts>[\d\- :]+)\] Client \d+ \((?P<client>[^)]+)\) '
                  r'(?P<ev>connected via (?P<path>\w+) connection|disconnected)')

def age(ts):
    try:
        t = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
        return time.time() - t
    except ValueError:
        return 1e9

def esc(v): return str(v).replace('\\', r'\\').replace('"', r'\"')

def main():
    lines = []
    sl = os.path.join(STEAM, "streaming_log.txt")
    try:
        with open(sl, errors="replace") as f: lines = f.readlines()
        mtime = os.path.getmtime(sl)
    except OSError:
        mtime = 0

    out = []
    def m(name, typ, help_, samples):
        out.append(f"# HELP steamlink_{name} {help_}")
        out.append(f"# TYPE steamlink_{name} {typ}")
        for labels, val in samples:
            lab = ",".join(f'{k}="{esc(v)}"' for k, v in labels.items())
            out.append(f"steamlink_{name}{{{lab}}} {val}" if lab else f"steamlink_{name} {val}")

    blame = collections.Counter()
    last_slow = last_net = None
    last_target = None
    for ln in lines:
        s = SLOW.search(ln)
        if s: blame[s["blame"]] += 1; last_slow = s; continue
        n = NET.search(ln)
        if n: last_net = n; continue
        t = TARGET.search(ln)
        if t: last_target = t

    m("log_last_modified_seconds", "gauge",
      "Unix time streaming_log.txt was last written", [({}, int(mtime))])
    m("slow_frames_total", "counter",
      "Slow-frame events Steam logged, by the stage Steam blamed",
      [({"blame": b}, c) for b, c in sorted(blame.items())] or [({"blame": "none"}, 0)])

    net_live = bool(last_net) and age(last_net["ts"]) < STALE
    m("streaming_active", "gauge",
      "1 if Steam reported a live stream connection within the stale window",
      [({}, 1 if net_live else 0)])

    if net_live:
        n = last_net
        relayed = 1 if n["route"].upper().startswith("SDR") else 0
        m("rtt_seconds", "gauge", "Round-trip time to the client",
          [({}, float(n["ping"]) / 1000)])
        m("relayed", "gauge",
          "1 if routed through a Steam Datagram Relay instead of peer-to-peer",
          [({"route": n["route"]}, relayed)])
        m("throughput_bytes_per_second", "gauge", "Stream throughput (Steam reports kbit/s)",
          [({"direction": "in"}, round(float(n["in_kbit"]) * 1000 / 8)),
           ({"direction": "out"}, round(float(n["out_kbit"]) * 1000 / 8))])
        m("packets_per_second", "gauge", "Packet rate",
          [({"direction": "in"}, n["in_pps"]), ({"direction": "out"}, n["out_pps"])])
        q = []
        for d, v in (("in", n["in_q"]), ("out", n["out_q"])):
            v = v.rstrip('%')
            if v.replace('.', '', 1).isdigit(): q.append(({"direction": d}, float(v) / 100))
        if q: m("quality_ratio", "gauge", "Connection quality reported by Steam (0-1)", q)

    if last_slow and age(last_slow["ts"]) < STALE:
        m("frame_stage_seconds", "gauge",
          "Per-stage frame time from Steam's most recent slow-frame report",
          [({"stage": st}, round(float(last_slow[st]) / 1000, 6)) for st in
           ("game", "capture", "convert", "encode", "network", "decode", "display")])

    if last_target:
        m("target_throughput_bytes_per_second", "gauge", "Throughput Steam is aiming for",
          [({"kind": "target"}, int(last_target["t"]) * 1000 // 8),
           ({"kind": "burst"}, int(last_target["b"]) * 1000 // 8)])

    # which clients have connected, and over what path
    conns = collections.Counter(); current = None
    rc = os.path.join(STEAM, "remote_connections.txt")
    try:
        with open(rc, errors="replace") as f:
            for ln in f:
                c = CONN.search(ln)
                if not c: continue
                if c["path"]:
                    conns[(c["client"], c["path"])] += 1
                    current = (c["client"], c["path"], c["ts"])
                elif current and current[0] == c["client"]:
                    current = None
    except OSError:
        pass
    m("client_connections_total", "counter",
      "Client connection events by client name and path (direct/indirect)",
      [({"client": k[0], "path": k[1]}, v) for k, v in sorted(conns.items())]
      or [({"client": "none", "path": "none"}, 0)])
    m("client_connected", "gauge",
      "1 for the client Steam most recently reported as connected (and not since disconnected)",
      [({"client": current[0], "path": current[1]}, 1)] if current
      else [({"client": "none", "path": "none"}, 0)])

    m("exporter_last_run_seconds", "gauge", "Unix time this exporter last ran",
      [({}, int(time.time()))])

    os.makedirs(OUT, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=OUT, prefix=".steamlink.", suffix=".tmp")
    with os.fdopen(fd, "w") as f: f.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(OUT, "steamlink.prom"))   # atomic: node_exporter never reads a partial file

if __name__ == "__main__":
    main()
