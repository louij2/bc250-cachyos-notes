# Monitoring LanCache with Prometheus and Grafana

LanCache monolithic ships no metrics endpoint. What it does have is an nginx
access log in a custom format that carries everything worth graphing, including
the cache result per request. Tailing that log with
[prometheus-nginxlog-exporter](https://github.com/martin-helmich/prometheus-nginxlog-exporter)
gives you real metrics without patching the container.

An importable dashboard lives at [`dashboards/lancache.json`](../dashboards/lancache.json).

## The log format

LanCache defines its own `log_format cachelog`. Get it from the container rather
than guessing:

```bash
docker exec lancache-monolithic sh -c 'grep -rh log_format /etc/nginx/'
```

```
[$cacheidentifier] $remote_addr / $http_x_forwarded_for - $remote_user
[$time_local] "$request" $status $body_bytes_sent "$http_referer"
"$http_user_agent" "$upstream_cache_status" "$host" "$http_range"
```

Two fields make the whole thing worthwhile:

- **`$cacheidentifier`** — which upstream the request belongs to (`steam`,
  `wsus`, `epicgames`, `riot`, …). It is the bracketed prefix at the start.
- **`$upstream_cache_status`** — `HIT`, `MISS`, `EXPIRED`, or `-`.

!!! warning "Don't grab the last field for cache status"
    `$upstream_cache_status` is **third from the end**, not last. Last is
    `$http_range`. Summing `$NF` gives you a meaningless wall of `"-"` and byte
    ranges, and makes it look like nothing is being cached:

    ```bash
    # WRONG - reads http_range
    awk '{print $NF}' access.log | sort | uniq -c

    # RIGHT - reads upstream_cache_status
    awk '{print $(NF-2)}' access.log | tr -d '"' | sort | uniq -c
    ```

There is also a `cachelog-json` format defined in the same file if you would
rather ship structured logs to Loki than parse positionally.

## Exporter config

```yaml
listen:
  port: 4040
  metrics_endpoint: /metrics

namespaces:
  - name: lancache
    format: '[$cacheidentifier] $remote_addr / $http_x_forwarded_for - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" "$upstream_cache_status" "$host" "$http_range"'
    source:
      files:
        - /var/log/lancache/access.log
    labels:
      instance: lancache
    relabel_configs:
      - target_label: service
        from: cacheidentifier
      - target_label: cache_status
        from: upstream_cache_status
```

Deliberately **not** labelled by client IP or request path. Both are unbounded
and will wreck Prometheus cardinality on a cache serving real traffic. If you
want per-client detail, ship the log to Loki and query it there.

Run it with the log directory bound read-only:

```
-v /path/to/lancache/logs:/var/log/lancache:ro
-v /path/to/exporter/config.yml:/etc/nginxlogexporter/config.yml:ro
```

If you already run this exporter for another nginx (SWAG, a reverse proxy),
run a **second instance on a different host port** rather than adding a
namespace to the existing one — the two have completely different log formats
and keeping them separate means a format change in one cannot break the other.

### Two harmless-looking things that are actually fine

- **`warn: No globs for /var/log/lancache/access.log`** at startup does *not*
  mean the mount failed. The exporter still tails correctly. Verify by
  generating a request and watching the metrics, not by trusting the warning.
- **The exporter only reports lines written after it starts.** It tails; it does
  not backfill. A freshly started exporter on an idle cache exposes nothing but
  `lancache_parse_errors_total 0`, which looks broken and isn't. Generate
  traffic to confirm:

  ```bash
  curl -s -o /dev/null -H 'Host: lancache.steamcontent.com' \
    'http://<lancache-ip>/lancache-heartbeat'
  curl -s http://127.0.0.1:<port>/metrics | grep '^lancache_'
  ```

Your historical log is *not* imported. Existing traffic stays a log file only.

## Prometheus

```yaml
  - job_name: 'lancache'
    static_configs:
      - targets: ['<unraid-ip>:4041']
        labels: { service_group: 'lancache' }
```

Validate before reloading — a bad config silently keeps the old one:

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://127.0.0.1:9090/-/reload
```

## Metrics you get

| metric | labels |
|---|---|
| `lancache_http_response_count_total` | `service`, `cache_status`, `status`, `method` |
| `lancache_http_response_size_bytes` | same |
| `lancache_parse_errors_total` | — |

Hit rate by bytes, which is the number that actually matters:

```promql
sum(rate(lancache_http_response_size_bytes{cache_status="HIT"}[5m]))
  / clamp_min(sum(rate(lancache_http_response_size_bytes[5m])), 1)
```

`clamp_min` avoids a divide-by-zero producing `NaN` panels while the cache is idle.

## Alerting

Grafana 10+ has unified alerting built in, so you do not need Alertmanager for
these. Rules worth having:

```promql
# Exporter stopped parsing - usually means the log format changed
rate(lancache_parse_errors_total[15m]) > 0

# Cache is being used but nothing is hitting - cache may be full, evicting,
# or the disk is read-only. Only alerts when there is real traffic.
sum(rate(lancache_http_response_size_bytes[30m])) > 1e6
  and
sum(rate(lancache_http_response_size_bytes{cache_status="HIT"}[30m]))
  / clamp_min(sum(rate(lancache_http_response_size_bytes[30m])),1) < 0.05

# Upstream errors
sum(rate(lancache_http_response_count_total{status=~"5.."}[10m])) > 0
```

Do **not** alert on a low hit rate alone. A cold cache legitimately sits near
0%, and it stays there until a *second* machine downloads something the first
one already pulled. One client will never generate hits, no matter how much it
downloads — worth understanding before you conclude your cache is broken.

## Unraid note

If you create the container with `docker run`, it becomes an "orphan" — it runs,
but the Docker tab cannot edit or update it. Write a template to
`/boot/config/plugins/dockerMan/templates-user/my-<name>.xml` matching the
container's `<Name>`, and Unraid adopts it. Copy an existing template as the
structural model; the `<Config>` entries must match the real ports and binds,
and any container arguments go in `<PostArgs>`.
