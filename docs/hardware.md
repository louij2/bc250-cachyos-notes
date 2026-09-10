# Hardware notes

## Display

**DisplayPort only** — there is no HDMI on the board. Passive DP→HDMI adapters
work better than active ones. Display output works in BIOS and Linux only.

DP connectors latch. A partially-seated one causes black screens, flicker and
image static — see [troubleshooting](troubleshooting.md).

## Power

`J1000` is a standard 8-pin PCIe connector. The community documentation
specifically calls for **16 AWG** wiring — this board pulls enough current that
undersized wire causes voltage droop and the resulting instability looks like
random hangs or GPU faults.

## Cooling

`J4003` drives **5× 80 mm fans**. These shipped in 4U rackmount chassis with
forced airflow. On a bench with no airflow the APU will throttle or cook,
especially with the unlocks applied.

## Jumpers worth knowing

| Header | Purpose |
|---|---|
| `AUTO_PWRON` | Board powers on automatically when power is applied — useful for an unattended machine |
| `CLRCMOS` | Proper CMOS reset. Better than pulling the CR2032 |
| `J4004` | SPI header for external BIOS flashing |

If BIOS settings appear to have reverted to defaults after transport, suspect a
weak CR2032 — and check **IOMMU**, which reverts to *enabled*.

## BIOS

- Stock version seen: `P3.00` (AMI, 12/09/2021)
- **IOMMU must be disabled** — it is broken on this board and causes black
  screens and instability
- Secure Boot disabled (required for the 40 CU unlock)
- CSM disabled, VRAM allocation 512 MB dynamic

`P3.00` is the correct base for the `MeiMeiDXE-T-v2` 8-core BIOS mod, but the
mod is not required — the Linux SMU method needs no flash.

## Kernel versions

Known to break `gfx1013`:

- `6.15.0` – `6.15.6`
- `6.17.8` – `6.17.10`

Known good: `6.18.18` LTS and later, `6.17.11+`. Verified working here:
`6.18.37-1-cachyos-lts`.

## GPU governor

The BC-250 needs a governor or it sits at a fixed clock/voltage combination that
is unstable under load.

- Arch: `oberon-governor`
- Fedora/Bazzite: `cyan-skillfish-governor-smu`

```bash
systemctl is-active oberon-governor cyan-skillfish-governor-smu
cat /sys/class/drm/card*/device/pp_dpm_sclk    # expect 500 / 1000 / 2000 MHz
```
