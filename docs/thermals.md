# Thermal results — liquid-cooled BC-250

Measured on a BC-250 with an AIO pump on the `Pump Fan` header (`fan2` on the
nct6686), no case fans connected. 8 cores unlocked, 40 CUs SPI-routed.
Kernel `6.18.37-1-cachyos-lts`.

## Test 1 — CPU only, 16 threads, 10 min

16 × `sha256sum /dev/zero`.

```
BASELINE  tctl=50.1  edge=47  vrm=41.5  ppt=32W   pump=1279
t=10s     tctl=67.2  edge=52            ppt=57W   pump=2086
t=33s     tctl=68.1  edge=52            ppt=57W   pump=2169
t=600s    tctl=68.1  edge=52            ppt=56W   pump=2131
```

**Plateaued at 68.1°C in 30 seconds, dead flat for 10 minutes.** All 8 cores
held 3493 MHz throughout — no throttling. VRM MOS 39.5°C.

## Test 2 — sustained GPU + CPU, 15 min

`glmark2-drm --run-forever` (needs the greeter stopped to take DRM master) plus
4 CPU threads. 88 samples, load verified alive at every sample.

| | Peak | Limit | Headroom |
|---|---|---|---|
| GPU edge | **73°C** | 85°C | 12°C |
| CPU Tctl | **74.9°C** | 90°C | 15°C |
| VRM MOS | **43.5°C** | — | — |
| NVMe | 41.9°C | 80°C | 38°C |
| PPT | **140 W** | — | (idle is 32 W) |
| Pump | 2521 RPM | max 2542 | ~20 RPM |

Curve across the full 15 minutes:

```
t=82s   tctl=69.2  edge=64   ppt=85W    pump=2197
t=267s  tctl=71.9  edge=65   ppt=81W    pump=2371
t=452s  tctl=70.1  edge=69   ppt=94W    pump=2226
t=637s  tctl=68.5  edge=60   ppt=69W    pump=2169
t=823s  tctl=72.1  edge=70   ppt=93W    pump=2371
```

**No upward drift.** Temperatures oscillate 65–75°C with load phase and never
trend up — this is a stable equilibrium, not heat soak. Zero throttling events,
zero GPU resets in `dmesg`.

## Comparison with the air-cooled reference

Upstream documentation measured **89.6°C average and 107°C peak** under
sustained load using dual Arctic P12 Max in push-pull, and concluded the stock
heatsink plus dual P12 Max is *"not enough headroom for sustained 40 CU at
2 GHz."*

A single AIO pump with no case fans peaked at **73°C** on the same measure —
**16°C below their average and 34°C below their peak.**

If you are running sustained compute on a BC-250, liquid cooling is a very large
improvement over even good high-static-pressure air, and the difference is far
bigger than the fan-choice differences the docs compare.

## Notes on measuring

- `PPT` is the honest load indicator: 32 W idle, 50–60 W CPU-only,
  85–140 W CPU+GPU. If PPT is not moving, your load is not landing.
- `sclk` sampled from `sensors` is near-useless — it reads instantaneously and
  usually catches an idle moment. Do not use it to confirm GPU load.
- The compute verifier alternates GPU dispatch with CPU golden comparison, so it
  is a *mixed* load. For a pinned GPU load use `glmark2-drm --run-forever`.
- `vkmark --winsys kms` fails with "Failed to find specified window system"
  unless the KMS winsys plugin is installed.
- Always assert your load is still alive at every sample. An early run here
  looked like a clean 15-minute pass but the load had died at 6 minutes.

## GPU correctness

`bc250-compute-verify.sh` over 268,435,456 elements: **0 errors, 0 int_errors,
0 fp_errors** — with all 40 CUs routed. No defective CUs on this board.
