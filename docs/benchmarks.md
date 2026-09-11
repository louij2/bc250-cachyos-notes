# Benchmarks

Measured numbers from a real BC-250, so there is something to compare against.
There is very little published baseline data for this board.

## Test system

| | |
|---|---|
| OS | CachyOS |
| Kernel | 6.18.48-1-cachyos-lts |
| Mesa / RADV | 26.2.2 |
| Governor | `cyan-skillfish-governor-smu` 0.4.11 |
| GPU range | 500–2000 MHz, throttle 85/75 |
| Unlocks | 8 cores (16 threads), 40 CU |
| Cooling | stock heatsink, single fan on the pump header |

## CPU — `stress-ng`, 16 threads, 90 s

```bash
stress-ng --cpu 16 --cpu-method all --metrics-brief --timeout 90s
```

| metric | value |
|---|---|
| bogo ops | 1,589,775 |
| bogo ops/s (real time) | 17,664.57 |
| sustained all-core clock | **3493 MHz** |
| peak Tctl | 76.2 °C |
| package power | 63–65 W |
| throttle events | none |

The sustained all-core clock is **above the top ACPI P-state of 3200 MHz**, and
it held for the full 90 s. If you enable the ACPI P-state tables and see
`scaling_available_frequencies` topping out at 3200000, the board can still
boost past that under load — the table is not the ceiling.

76 °C peak against an 85 °C throttle point means stock cooling is not the
limiting factor for CPU-bound work.

## GPU — `vkmark`, inside gamescope

Score **8708** — but read the caveat.

All 13 scenes landed within 5% of each other (8462–8952). On a real GPU-bound
run those scenes spread out substantially. Clustering that tightly means the
run was bound by the compositor and the window size, not the GPU.

!!! warning "Benchmarking a box that is in Game Mode"
    Running `vkmark` or `glmark2` over SSH against a live gamescope session
    measures the compositor, not the GPU. The numbers are repeatable, so they
    are fine for before/after on one machine, but they are meaningless across
    machines.

    To run it at all, you need the session's Wayland socket:

    ```bash
    export XDG_RUNTIME_DIR=/run/user/$(id -u)
    export WAYLAND_DISPLAY=$(ls $XDG_RUNTIME_DIR | grep -E '^gamescope-[0-9]+$' | head -1)
    vkmark
    ```

    For a GPU number worth comparing, use a fullscreen runner or an offscreen
    Vulkan workload instead. Note the docs' warning that
    `glmark2 --off-screen` is not a valid GPU load test on a headless box.

## Publishing comparable scores

Geekbench 6 is the only common benchmark that runs on the BC-250, a Steam Deck
**and** Windows, so it is the one that gives directly comparable numbers across
a mixed estate. Phoronix Test Suite is Linux-only but far better for GPU.

!!! warning "Upgrade fully first"
    Installing a benchmark via an AUR helper on a system with pending updates
    will either partial-upgrade you or pull the whole backlog. A partial upgrade
    is how you end up with `vulkan-radeon` built against a different `mesa`,
    which produces amdgpu ring timeouts that look like a game bug. Always
    `pacman -Syu` first, never `-Sy`.

```bash
sudo pacman -Syu
yay -S geekbench6 phoronix-test-suite
geekbench6                 # CPU, prints a public result URL
geekbench6 --vulkan        # GPU
phoronix-test-suite benchmark pts/unigine-heaven
```

Geekbench's free version uploads results publicly — that is what produces the
shareable URL. It publishes CPU/GPU/RAM/OS details. There is no way to make a
result private afterwards.

## Measuring the overclock properly

Raising the governor ceiling is only worth it if you can show it helped:

1. Benchmark at the current ceiling and keep the result URL.
2. Raise `[frequency-range] max` and the top of the voltage curve.
3. Re-run the identical benchmark.
4. Revert if it regressed or destabilised.

Keep a backup of the config so step 4 is one command:

```bash
sudo cp /etc/cyan-skillfish-governor-smu/config.toml{,.bak}
```

Do this at the machine. An unstable GPU clock hard-locks the board, and the
only recovery is the physical power switch.
