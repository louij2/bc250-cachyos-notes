# Steam Deck-style Game Mode on CachyOS

Turning a BC-250 into a console-style Steam machine: boot straight into Steam
Big Picture, no greeter, no lock screen, with Decky Loader for plugins.

## Packages — use the CachyOS ones, not the AUR

CachyOS ships this natively. Do **not** go to the AUR:

```bash
sudo pacman -S gamescope-session-cachyos jupiter-hw-support
```

`gamescope-session-cachyos` is "Steam Big Picture session based on gamescope
from SteamOS". It **conflicts with** `gamescope-session-git` and
`gamescope-session-steam-git`, so if you installed either of those first,
remove them:

```bash
sudo pacman -Rdd gamescope-session-git
```

It installs `/usr/share/wayland-sessions/gamescope-session.desktop` plus
`steamos-session-select`, the Deck's own Game Mode ↔ Desktop switcher.

## Autologin — plasmalogin, not SDDM

Plasma 6.7 on CachyOS uses **plasmalogin**, not SDDM. Check before you write
config to the wrong place:

```bash
readlink -f /etc/systemd/system/display-manager.service
```

Config is `/etc/plasmalogin.conf`, same format SDDM used:

```ini
[Autologin]
User=youruser
Session=gamescope-session
Relogin=false
```

If the `User=` names an account that no longer exists, autologin fails silently
and you land on the greeter. Second-hand machines often carry the previous
owner's username here.

## The big one: gamescope dies if the monitor is asleep at boot

**Symptom:** black screen with a working mouse cursor after enabling Game Mode.
The journal shows the autologin session opening and closing about one second
later, then a greeter session starting instead.

**Cause:**

```
[gamescope] drm: Connectors:
[gamescope] drm:   DP-2 (disconnected)
[gamescope] drm:   DP-1 (disconnected)
[gamescope] drm: cannot find any connected connector!
[gamescope] Error drm: Failed to find a primary plane
gamescope-session.service: Main process exited, code=exited, status=1/FAILURE
```

**gamescope enumerates DRM connectors exactly once at startup and exits if none
are connected. It does not retry.** A monitor in standby reports
`disconnected` until the link trains, and gamescope starts ~13 s after boot —
often before that happens. Plasma tolerates this; gamescope does not.

Everything downstream then fails with `Failed to load environment files: No such
file or directory`, because `gamescope-session` never got far enough to write
`/run/user/$UID/gamescope-environment`, which `steam-launcher`,
`gamescope-mangoapp` and the rest read via `EnvironmentFile=%t/gamescope-environment`.
Those are symptoms, not the fault — don't chase them.

**Fix** — wait for a connector before starting:

```bash
sudo mkdir -p /etc/systemd/user/gamescope-session.service.d
sudo tee /etc/systemd/user/gamescope-session.service.d/10-wait-for-display.conf <<'CONF'
[Service]
ExecStartPre=/usr/bin/bash -c 'for i in $(seq 1 45); do for s in /sys/class/drm/card*/card*-*/status; do [ "$(cat "$s" 2>/dev/null)" = "connected" ] && exit 0; done; sleep 1; done; exit 0'
CONF
sudo systemctl daemon-reload
```

The final `exit 0` matters: after 45 s it starts anyway rather than blocking the
boot forever.

Confirm it worked — you want a named connector, not "disconnected":

```
[gamescope] drm: Connector DP-1 -> ACR - R241Y
```

## Optional units that fail noisily

`gamescope-session-cachyos` has optional dependencies whose units are enabled
regardless. They fail with `status=203/EXEC` when the binary is absent:

| Unit | Needs | Worth it? |
|---|---|---|
| `gamescope-xbindkeys` | `xbindkeys` | Yes — hotkeys |
| `ibus-gamescope` | `ibus` | Only for multilingual input |
| `steam-notif-daemon` | `steam_notif_daemon` | Not packaged on Arch |

`xbindkeys` also needs a config file to exist or it exits 255:

```bash
sudo pacman -S xbindkeys
xbindkeys --defaults | sudo tee /etc/xbindkeysrc
```

## Decky Loader

The installer URL in most guides is **deprecated** and now only prints a
redirect. Current one:

```bash
curl -sL -o decky.sh https://github.com/SteamDeckHomebrew/decky-installer/raw/main/cli/install_release.sh
sudo bash decky.sh
```

It needs `jq`. It is distro-agnostic — no SteamOS-specific assumptions — and
uses `$SUDO_USER` to find the home directory, so run it with `sudo` from your
normal user, not as root directly.

## Migrating from a real Steam Deck

**Controller layouts are in Steam Cloud, not on disk.** `controller_config/` is
typically empty and `controller_base/templates/` holds Valve's stock templates,
not yours. They sync on login — there is nothing to copy.

Worth copying from `userdata/<steamid>/config/`, *after* first Steam login on
the new machine so the tree exists:

- `shortcuts.vdf` — non-Steam shortcuts, these do **not** cloud-sync
- `compat.vdf` — per-game Proton assignments

**Do not copy** `loginusers.vdf` or `ssfn*` — Steam auth and Steam Guard machine
tokens. Log in fresh instead.

CSS Loader themes in `~/homebrew/themes/` are plain files and safe to copy.

Deck-hardware plugins install but have nothing to talk to on a BC-250:
PowerTools (Deck SMU/TDP), Fantastic (Deck fan), ControllerTools (built-in
controller), and anything battery-related.
