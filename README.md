# AMD BC-250 on CachyOS — field notes

Working notes from setting up a second-hand **AMD BC-250** (semi-custom PS5
"Ariel" APU, Cyan Skillfish / `gfx1013`, `1002:13fe`) as a Linux gaming console
running **CachyOS**.

This is deliberately a *field* record — the things that actually went wrong and
what the symptom looked like at the time, not a rewritten tidy guide. The
excellent reference documentation already exists; see [Credits](#credits).

## Hardware as received

| | |
|---|---|
| APU | AMD BC-250 (Zen 2 + RDNA2, `gfx1013`) |
| Stock config | **6 cores / 12 threads**, **24 of 40 CUs** |
| Unlocked | 8 cores / 16 threads, 40 CUs |
| RAM | 16 GB GDDR6 (shared) |
| BIOS | `P3.00`, AMI, dated 12/09/2021 |
| Display out | **DisplayPort only** |
| Storage | NVMe |

## Contents

- [`docs/troubleshooting.md`](docs/troubleshooting.md) — real failures and their causes
- [`docs/unlocks.md`](docs/unlocks.md) — 8-core and 40 CU unlocks, and their persistence models
- [`docs/gamemode.md`](docs/gamemode.md) — Steam Deck-style Game Mode, Decky, and the gamescope display race
- [`docs/thermals.md`](docs/thermals.md) — measured thermal results, liquid-cooled, vs the air-cooled reference
- [`docs/multi-device.md`](docs/multi-device.md) — syncing saves/themes across machines, Remote Play, emulator sandboxing
- [`docs/storage.md`](docs/storage.md) — portable games/media drive: one btrfs pool, no fixed split
- [`docs/pacman-mirrors.md`](docs/pacman-mirrors.md) — upgrade 404s that were a bad mirror, not the repos
- [`docs/hardware.md`](docs/hardware.md) — board notes: power, cooling, jumpers
- [`docs/remote-power.md`](docs/remote-power.md) — running it headless: DP dummy plug, Wake-on-LAN, remote power off/on
- [`scripts/setup.sh`](scripts/setup.sh) — one-shot gaming + unlock setup for CachyOS

## The single most useful thing in here

**The 8-core unlock lives in a volatile SMU register.** A warm reboot keeps it;
removing power resets it to the factory `0x77` mask. If you buy a board
advertised as "8 cores unlocked" and it arrives showing 6, nothing is wrong and
nobody lied to you — you cold-booted it. See [`docs/unlocks.md`](docs/unlocks.md).

## Credits

Everything here builds on community work:

- [elektricM/amd-bc250-docs](https://github.com/elektricM/amd-bc250-docs) — the reference documentation
- [mothenjoyer69/bc250-documentation](https://github.com/mothenjoyer69/bc250-documentation) — hardware/pinouts
- [GabriWar/bc250-core-cu-unlock](https://github.com/GabriWar/bc250-core-cu-unlock) — 8-core + CU + ACPI scripts
- [duggasco/bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock) — 40 CU unlock and verification tooling
- [WinnieLV/bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager) — runtime CU manager
- [mendesrr/bc250-acpi-fix-updated-8c](https://github.com/mendesrr/bc250-acpi-fix-updated-8c) — 8-core ACPI tables
