# Running the BC-250 headless

The BC-250 is DisplayPort-only and has no onboard video fallback, which makes
"headless" a slightly different problem to a normal PC. Two things bite.

## gamescope enumerates connectors once, at startup

Game Mode (`gamescope-session`) walks the DRM connectors when it starts. If it
finds none connected it exits immediately — the session dies and you get a
black screen with no obvious cause.

Crucially it only checks **at startup**. Once gamescope is running, you can
power the monitor off and the session survives:

```bash
# monitor physically switched off, mid-session
cat /sys/class/drm/card*/card*-DP-1/status   # disconnected
pgrep -c gamescope                            # still running
```

So in-place streaming (Steam Link, Remote Play) keeps working with the display
off. But **rebooting** with the display off will not come back — gamescope
starts, sees nothing, and exits.

### Fix: a DisplayPort dummy plug

A passive DP dummy plug (~£5) presents a permanent connected sink with a sane
EDID. The connector reads `connected` regardless of what the real monitor is
doing, so the session starts reliably whether or not a screen is attached.

This is the only fix that holds across an unattended reboot. The startup-delay
workaround below helps a monitor that is *slow to wake*, but cannot help when
there is genuinely nothing plugged in.

```ini
# /etc/systemd/user/gamescope-session.service.d/10-wait-for-display.conf
[Service]
ExecStartPre=/usr/bin/bash -c 'for i in $(seq 1 45); do for s in /sys/class/drm/card*/card*-*/status; do [ "$(cat "$s" 2>/dev/null)" = "connected" ] && exit 0; done; sleep 1; done; exit 0'
```

Also pin the output, since the SteamOS default targets a Steam Deck panel that
does not exist on this board:

```ini
# /etc/systemd/user/gamescope-session.service.d/20-output-connector.conf
[Service]
Environment=OUTPUT_CONNECTOR=DP-1
```

## Remote power off / on

### Off

```bash
ssh <host> 'sudo systemctl poweroff'
```

### On — Wake-on-LAN

The onboard NIC is a Realtek `r8169`. Check what it supports:

```bash
sudo ethtool <iface> | grep -i wake-on
#   Supports Wake-on: pumbg
#           Wake-on: g          <- g = magic packet
```

`g` is what you want. Two things have to be true for it to work from a full
power-off (S5), and people usually only do the first:

1. **The NIC is armed at the moment of shutdown.** NetworkManager can own this:

   ```bash
   nmcli connection modify <conn> 802-3-ethernet.wake-on-lan magic
   ```

   `r8169` in particular can drop the setting on some shutdown paths, so it is
   worth arming it explicitly on the way down as well:

   ```ini
   # /etc/systemd/system/wol-arm.service
   [Unit]
   Description=Arm Wake-on-LAN (at boot and before shutdown)
   After=network.target
   DefaultDependencies=no
   Before=shutdown.target

   [Service]
   Type=oneshot
   RemainAfterExit=yes
   ExecStart=/usr/bin/ethtool -s <iface> wol g
   ExecStop=/usr/bin/ethtool -s <iface> wol g

   [Install]
   WantedBy=multi-user.target
   ```

2. **The BIOS allows PCI-E to wake the board.** On the AMI BIOS used here this
   lives under power management ("Wake on PCI-E", "Power On By PCI-E/PCI", or
   similar). If this is off, the OS side is armed and nothing happens — the NIC
   loses power in S5. **This is the part you cannot verify remotely**, so test a
   full power-off cycle while you are physically at the machine.

### Magic packets do not route

A WoL packet is an L2 broadcast. It does not cross a router, so it cannot be
sent from outside the LAN — including over a VPN like Tailscale. You need an
always-on host **on the same broadcast domain** to send it.

On an OPNsense/pfSense box (FreeBSD ships `wake(8)`):

```sh
/usr/sbin/wake <lan-iface> <mac>
```

On Linux, `wakeonlan` or `etherwake`. Note that some NAS platforms ship neither
and also block raw broadcast writes from the shell, in which case a small
container or the firewall is the easier host.

### The bulletproof alternative

If the BIOS will not wake on PCI-E, use a smart plug plus the BIOS "restore
power state after AC loss" setting set to **On**. Cutting and restoring mains
then boots the machine. Cruder, but it does not depend on the NIC.

## Make sure it cannot go to sleep instead

A box you intend to wake with WoL should not be half-asleep in a state you did
not plan for. Confirm suspend is genuinely impossible:

```bash
systemctl status sleep.target suspend.target hibernate.target hybrid-sleep.target \
  | grep -E 'Loaded|masked'
journalctl --list-boots >/dev/null && journalctl -b --no-pager | grep -ci suspend
```

To mask them:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```
