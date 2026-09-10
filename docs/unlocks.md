# Unlocks — 8 cores and 40 CUs

Stock BC-250 is **6 cores / 12 threads** and **24 of 40 CUs**. Neither is
physically damaged; both are masked in firmware.

## Is it already unlocked? Check properly

```bash
lscpu | grep -E '^CPU\(s\):|Core\(s\) per socket'
cat /sys/devices/system/cpu/present          # 0-11 stock, 0-15 unlocked
RADV_DEBUG=info vulkaninfo --summary | grep num_cu
./scripts/cu_map.sh                          # from duggasco/bc250-40cu-unlock
```

### Three tools, three different answers — only one is right

This cost us a lot of confusion, so it is worth being explicit:

| Tool | Reports | Why |
|---|---|---|
| `vulkaninfo` `num_cu` | **24** | What amdgpu enumerated at driver init. Never changes. |
| `cu_map.sh` (duggasco) | **24/40** | Reads the driver's CC/harvest registers only. |
| `bc250-cu-live-manager status` | **40/40** | Reads CC *and* the SPI dispatch masks. |

**`bc250-cu-live-manager status`, run as root, is the authoritative view.**

The runtime unlock does not change what the driver enumerated — it routes the
extra WGPs via **SPI dispatch masks**. The dashboard's legend makes this
explicit: `D+` is driver-enumerated and routed, `S+` is SPI-routed. A working
40 CU system shows three `D+` and two `S+` per shader array:

```
| Row     | WGP0 | WGP1 | WGP2 | WGP3 | WGP4 | SPI  | CUs   |
| SE0.SH0 |  D+  |  D+  |  D+  |  S+  |  S+  | 0x1f | 10/10 |
...
CUs active & routed : 40/40
```

So `cu_map.sh` reporting 24/40 does **not** mean the unlock failed — it means
that tool cannot see SPI routing. Check the live manager dashboard before
concluding anything is broken.

Also note `umr` **silently needs root**. Run `cu_map.sh` unprivileged and it
prints a plausible-looking 24/40 built from a failed register read:

```
[ERROR]: ASIC not found or compatible (instance=256, did=ffffffffffffffff)
[ERROR]: UMR was not invoked as root.
```

### Proving the BIOS is not delivering 8 cores

```bash
cat /sys/devices/system/cpu/present   # 0-11
cat /sys/devices/system/cpu/offline   # empty
```

If the BIOS were presenting 8 cores, `present` would read `0-15` and the extras
would appear as *offline*. Only 12 logical CPUs existing means they are masked
below the OS. Conclusive — no need to guess from a BIOS version string.

## 8-core unlock — and why it "disappears"

The two extra cores are masked by SMN register `0x0115A870` — the core enable
bitmask, `0x77` from the factory, `0xFF` for all eight. It is flipped through an
SMU mailbox command (message `0x98`).

> **A warm reset preserves the mask. A cold boot — power actually removed —
> resets it to `0x77`.**

That is the built-in escape hatch, and it explains a very common confusion:

**A board genuinely running 8 cores at the seller's house will show 6 when it
reaches you.** You unplugged it. Nothing was lost or reset in software; the
register lost power. Files on disk (firewall rules, configs) survive because
they are files. The core mask is not a file.

```bash
git clone https://github.com/GabriWar/bc250-core-cu-unlock
cd bc250-core-cu-unlock
sudo ./bc250-8core-unlock.sh status
sudo ./bc250-8core-unlock.sh apply
sudo ./bc250-8core-unlock.sh install   # systemd unit, re-applies at every boot
sudo reboot                            # WARM. Do not cut power.
```

### Do not skip the ACPI tables

The stock ACPI tables describe 6 cores, leaving the 4 new threads with no
C-states.

```bash
sudo ./bc250-acpi-fix.sh install
```

## 40 CU unlock

16 CUs are fused off in firmware and re-enabled at the driver level. Two
approaches:

**Kernel module patch** — `duggasco/bc250-40cu-unlock`, `bc250-enable-40cu-arch.sh`.
Reverts on every kernel update, so you rebuild or pin. Poor fit for a rolling
distro.

**Runtime manager** — `WinnieLV/bc250-cu-live-manager`. Writes dispatch registers
at boot via a systemd unit, survives kernel updates. Better fit for CachyOS.

Config lives at `/etc/bc250-cu-live-manager.conf`:

```
BC250_WGP_MASKS=0x1f,0x1f,0x1f,0x1f
UMR_ASIC=cyan_skillfish.gfx1013
```

`0x1f` = 5 WGPs = 10 CUs per shader array × 4 arrays = 40.

Requires Secure Boot disabled.

### Expectations

Measured benefit on **graphics** workloads is roughly **+4.4%**. This is a
compute-oriented unlock — worth it for ML and GPGPU, close to noise for gaming.
The 8-core unlock is the one that helps games.

## Before you unlock anything

Both unlocks raise power draw and heat. Sustained 2 GHz across 40 CUs throttles
on the stock heatsink. The board is a **blade designed for chassis airflow**
(`J4003` drives 5× 80 mm fans) and the power input expects **16 AWG** wiring —
undersized wire causes droop, which reads as random instability.

Check `sensors` under sustained load, not at idle. Idle numbers tell you nothing.
