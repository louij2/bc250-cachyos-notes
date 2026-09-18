# LLM inference on the BC-250

The BC-250 is a genuinely good local inference node, for one reason: **16 GB of
GDDR6**. Not speed — capacity and memory bandwidth. It holds models an 8 GB
discrete card cannot touch, and generates faster than any CPU in the house.

Measured 2026-09-17/18 on CachyOS, kernel `6.18.48-1-cachyos-lts`, 8 cores
unlocked (16 threads), 40 CUs, `cyan-skillfish-governor-smu` active.

## ROCm is not the path — Vulkan is

`gfx1013` (Cyan Skillfish) is **not a supported ROCm target**. Do not burn an
evening on `HSA_OVERRIDE_GFX_VERSION` incantations. The Vulkan backend via RADV
works, is packaged, and is what everything below was measured on.

That does mean llama.cpp/ollama only. No vLLM, no exllama, no tensor parallel.

```bash
sudo pacman -S --needed ollama-vulkan
```

Confirmation you are actually on the GPU — this line in the journal is the
whole game:

```
msg="inference compute" id=0 library=Vulkan name=Vulkan0 \
  description="AMD BC-250 (RADV GFX1013)" type=iGPU \
  total="15.3 GiB" available="14.7 GiB"
```

If `ollama ps` says `100% CPU`, the Vulkan runner did not load and there is no
point continuing.

## The trap: a hand-installed ollama shadows the packaged one

This is the failure that actually cost time, and it presents as something else
entirely.

A manually installed ollama (the `curl | sh` route) drops a binary at
`/usr/local/bin/ollama` **and a unit file at `/etc/systemd/system/ollama.service`**.
Units in `/etc` override those in `/usr/lib`. So after installing the packaged
`ollama-vulkan` and removing the old binary, systemd still runs the *old* unit,
still pointing at the deleted path:

```
ollama.service: Unable to locate executable '/usr/local/bin/ollama': No such file or directory
ollama.service: Failed at step EXEC spawning /usr/local/bin/ollama
ollama.service: Main process exited, code=exited, status=203/EXEC
ollama.service: Scheduled restart job, restart counter is at 20.
```

`systemctl enable` reports success, `systemctl status` says `activating
(auto-restart)`, and the CLI just says *"could not connect to a running Ollama
instance"* — which reads like a networking problem and is not one.

Two more tells that you are on the hand-rolled unit:

- the manual unit is `WantedBy=default.target`, so enabling it symlinks into
  `default.target.wants`, not `multi-user.target.wants`
- the manual install ships only a `cuda_v12` runner in `/usr/local/lib/ollama`,
  so even when it *does* start, on this board it silently runs **pure CPU** —
  no better than a tower with no GPU at all

Fix:

```bash
sudo systemctl disable --now ollama
sudo cp -a /etc/systemd/system/ollama.service /root/ollama-unit-backup.service
sudo rm -f /etc/systemd/system/ollama.service
sudo rm -f /etc/systemd/system/default.target.wants/ollama.service
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
systemctl show ollama -p ExecStart --value   # must read /usr/bin/ollama
```

Keep any drop-ins in `/etc/systemd/system/ollama.service.d/` — those apply to
the packaged unit and survive the swap.

## Measured throughput

Same ~3.8–4.5k token prompt in every run, generation capped at 300 tokens.
All fully GPU-resident unless noted.

| Model | Context | Generation | Prefill | Peak Tctl |
|---|---|---|---|---|
| `qwen2.5-coder:7b` (dense) | 32k | 56.6 tok/s | 408 tok/s | 70.9 °C |
| `deepseek-coder-v2:16b-lite` (MoE) | 8k | **89.1 tok/s** | **746 tok/s** | 72.9 °C |
| `deepseek-r1:14b` (dense) | 8k | 27.7 tok/s | 217 tok/s | — |
| `deepseek-r1:14b` (dense) | 32k | 28.3 tok/s | 218 tok/s | 82.1 °C |

For scale, the same 7B model on other hardware:

| Host | Stack | Generation | Prefill |
|---|---|---|---|
| Ryzen 9 3900X | CPU | 8.1 tok/s | 54 tok/s |
| Ampere Altra | CPU | 4.6 tok/s | 190 tok/s |
| **BC-250** | **Vulkan** | **56.6 tok/s** | **408 tok/s** |
| RX 6800 XT | Vulkan | 83.5 tok/s | 515 tok/s |
| RTX 3060 Ti | CUDA | 81 tok/s | 3095 tok/s |

## Prefer MoE — the 16B is faster than the 7B

The single most useful result here. `deepseek-coder-v2:16b-lite` generates at
**89 tok/s against the dense 7B's 57**, despite being more than twice the size,
because only ~2.4B parameters are active per token. Quality is 16B-class.

On a bandwidth-bound GPU with no matrix cores, MoE is the shape to reach for.
It also beats the RTX 3060 Ti's 81 tok/s — and the 3060 Ti cannot run this model
at all, because 10 GB of weights will not fit in 8 GB. **That is the BC-250's
actual contribution: models other cards cannot hold.**

## Context is the hard limit — and it is per model

The GDDR6 is shared with system RAM, so the KV cache competes with everything
else on the box, the desktop included. The safe context differs sharply by
architecture, and one model's ceiling tells you nothing about another's:

```
deepseek-coder-v2 16B MoE @ 32k -> 3 layers overflow, then OOM-killed the service
deepseek-coder-v2 16B MoE @  8k -> 28/28 layers on GPU, host buffer 112 MiB, stable
deepseek-r1       14B dense @  8k -> 49/49 layers, KV cache  432 MiB
deepseek-r1       14B dense @ 32k -> 49/49 layers, KV cache 1728 MiB, still 100% GPU
```

So the *16B* needs 8k while the *14B* is comfortable at 32k — the MoE's KV
footprint per token is far larger. Raising the 14B to 32k cost nothing at all
(28.3 vs 27.7 tok/s), which matters for a reasoning model that needs room to
think.

!!! warning "A too-large num_ctx looks like a dead backend, not a slow one"
    With `OOMScoreAdjust=1000` on the unit, the kernel kills ollama rather than
    the desktop. That is the right choice for a dual-purpose box — but it means
    an oversized context does not degrade gracefully. The service simply dies:

    ```
    ollama.service: Failed with result 'oom-kill'.
    ```

    Pin `num_ctx` per model in whatever is calling you. Do **not** rely on the
    daemon's `OLLAMA_CONTEXT_LENGTH`, which defaults high enough to kill a 16B.

## Thermals under inference

Inference is a more sustained load than gaming bursts, and model architecture
changes it more than model size does:

| Workload | Peak Tctl | Headroom to 85 °C throttle |
|---|---|---|
| 7B dense | 70.9 °C | 14 °C |
| 16B MoE | 72.9 °C | 12 °C |
| **14B dense** | **82.1 °C** | **3 °C** |

The dense 14B is the hottest workload recorded on this board — hotter than the
CPU and GPU stress tests in [thermals](thermals.md) — because all 49 layers are
active on every token, unlike the MoE's ~2.4B. It is also the model most likely
to run long, since R1 emits lengthy `<think>` blocks before answering.

On the stock heatsink with a single fan, that is 3 °C of margin. The board
expects 5 × 80 mm of forced air; see [hardware](hardware.md). If you intend to
run a dense 14B for any length of time, fix the airflow first.

## Where this fits

Prefill is the ceiling. Even the MoE's 746 tok/s is a quarter of the 3060 Ti's
3095, and far below the ~2000 tok/s that agentic coding needs — a full-size
prompt costs tens of seconds before the first token appears.

That makes the BC-250 a **batch/offload node**: bounded inputs, recurring
automation, classification, summarising, commit messages. It is not an
interactive coding backend and no amount of tuning will make it one.

It is also **dual-purpose**. This board is the gaming console; 16 GB shared
means a loaded game and a loaded 9 GB model do not coexist. Treat it as
best-effort in whatever routes to it, and stop the service before gaming:

```bash
sudo systemctl stop ollama
```

## Notes on measuring

- **Use a large prompt.** A short one reports warm-cache noise, not prefill
  throughput. Everything above used ~3.8–4.5k tokens.
- **`ollama ps` is the honest check.** `100% GPU` and the `CONTEXT` column tell
  you both that the Vulkan runner loaded and what context actually got applied
  — which is often not what you asked for.
- **Watch the fit log before blaming speed.** These lines appear at load and say
  whether anything spilled to system memory:

    ```bash
    journalctl -u ollama | grep -E "offloaded [0-9]+/|buffer size|overflow"
    ```

    `offloaded 28/28 layers to GPU` with a small `Vulkan_Host` buffer is what
    you want. A large host buffer, or `N overflowing`, means the context is too
    big and the OOM kill is coming.
- **Temperature immediately after a run, not during.** Tctl lags; sampling mid-
  generation under-reads the peak.
