# Multi-device gaming: sync, streaming, emulation

Notes from wiring three machines into one setup — a BC-250 (CachyOS), a Steam
Deck (SteamOS) and a Windows PC — so saves, themes and emulator state follow you
between them.

## Parsec cannot host on Linux

Verified against Parsec's own support docs (May 2026):

> "Parsec does not support hosting on Linux systems, you can only use it to
> connect to other devices."
>
> "hosting is currently only available on Windows and macOS computers."

Aggregator sites claiming otherwise are wrong. Practical consequence:

| Device | Parsec host | Parsec client |
|---|---|---|
| Linux (any distro) | no | yes |
| Windows / macOS | yes | yes |

**Do not** restructure a Linux box's session (e.g. switching a gamescope
session to Plasma) to enable Parsec hosting. It will not work. Use **Steam
Remote Play**, which hosts natively on Linux and Windows in both directions.

## Steam Remote Play makes games look duplicated

Once two machines share a Steam account, each advertises its installed games to
the other. A game installed on machine A appears in machine B's library as
*"Play on A"* alongside anything installed locally. That is Remote Play working,
not duplicate shortcuts.

To hide them, use the library filter's streaming toggle. Check `shortcuts.vdf`
before assuming you have real duplicates:

```bash
python3 -c "
import vdf, collections
d=vdf.binary_load(open('shortcuts.vdf','rb'))['shortcuts']
c=collections.Counter(v['AppName'] for v in d.values())
print({n:x for n,x in c.items() if x>1} or 'no duplicates')"
```

Set a **permanent Remote Play security code** (Steam → Settings → Remote Play)
rather than relying on one-time pairing PINs. Pairing itself is UI-only — the
PIN drives a cryptographic handshake, so there is no config file to write and no
CLI to script.

## Syncthing between hosts

Syncthing is the right tool for the parts Steam Cloud does not cover. Steam
already syncs controller layouts and cloud saves; it does **not** sync emulator
saves, BIOS files, ROMs or Decky state.

Install, then create a user service (works on immutable SteamOS — nothing
touches the read-only filesystem):

```bash
mkdir -p ~/.local/bin ~/.config/systemd/user
# download the release tarball, put the binary in ~/.local/bin
cat > ~/.config/systemd/user/syncthing.service <<'UNIT'
[Unit]
Description=Syncthing
After=network.target
[Service]
ExecStart=%h/.local/bin/syncthing serve --no-browser --no-restart --logflags=0
Restart=on-failure
SuccessExitStatus=3 4
[Install]
WantedBy=default.target
UNIT
systemctl --user enable --now syncthing
```

Pair and create folders via the REST API rather than the GUI — the API key is in
`~/.local/state/syncthing/config.xml`:

```bash
KEY=$(grep -oE '<apikey>[^<]+' ~/.local/state/syncthing/config.xml | head -1 | sed 's/<apikey>//')
curl -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8384/rest/config/devices \
  -d '{"deviceID":"PEER-ID-HERE","name":"peer","addresses":["dynamic"]}'
```

Set `ignorePerms: true` on every shared folder — the two machines run different
usernames (`deck` vs whatever), and without it every file reports a permission
conflict.

### What to sync, and what not to

| Sync | Don't sync |
|---|---|
| `~/Emulation/saves`, `storage`, `bios` | `shortcuts.vdf` |
| `~/homebrew/settings`, `data`, `themes` | non-Steam artwork (`config/grid`) |
| ROMs, cheats | `~/homebrew/plugins` (root-owned, version-specific) |

**`shortcuts.vdf` must never be synced.** Non-Steam appids are derived from the
exe path plus the name, and those paths differ between SteamOS, Arch and
Windows. A synced file points at binaries that do not exist. Non-Steam artwork
is named by those same appids, so it cannot be synced either — it has to be
remapped per machine.

### The CSS Loader trap

Decky's CSS Loader stores each theme's enabled state **in the theme directory**,
as `"active": true` inside `config_USER.json`. Syncing `~/homebrew/themes`
therefore syncs *which themes are on*, not just the theme files.

That matters because themes authored for the Deck's 1280x800 panel — anything
with "Layout", "Grid", "Carousel" or "Home" in the name — break a 1920x1080
display. The failure looks alarming: **black screen, but the QAM overlay still
renders**, because the overlay rules happen to survive while the home page rules
do not.

Fix: sync the files, never the state.

```bash
printf 'config_USER.json\n' > ~/homebrew/themes/.stignore
```

Then use **CSS Loader profiles** — one per device, since profiles capture pixel
values (`Hero Height`, `Carousel Height`, `Blur Strength`) tuned for one screen.
A profile is stored as `<name>.profile/theme.json`, lives inside the themes
folder, and so syncs to every machine while each picks its own.

Also note CSS Loader caches its theme list at plugin load. A profile that
arrives via sync will not appear until Decky reloads.

## Emulator flatpaks cannot see external drives

This one silently breaks everything. Default RPCS3 sandbox:

```
filesystems=home:ro;/media;xdg-config/kdeglobals:ro;/run/media;
```

`home:ro` is **read-only**, and `/mnt` is absent entirely. Point EmuDeck at
`/mnt/roms` and every emulator will fail to find a single file with no useful
error. Grant access explicitly:

```bash
sudo flatpak override --filesystem=/mnt/roms net.rpcs3.RPCS3
# repeat for every emulator, or use --filesystem=$HOME/Emulation on SteamOS
```

## RPCS3

**Firmware is mandatory** and cannot be shipped with the emulator. Download
`PS3UPDAT.PUP` from Sony's official support site.

Installing it needs the GUI — `--installfw` exists but the flow is a Qt dialog,
so it fails headless under both `QT_QPA_PLATFORM=offscreen` and a Wayland
socket. Use **File → Install Firmware** in the app.

**Disc format: ISOs now work.** RPCS3 historically required extracted "JB"
folders; it now loads decrypted `.iso`, Redump encrypted `.iso` + `.dkey`, and
3k3y images directly, decrypting on the fly. Folder dumps remain supported.
Keep `.dkey` files in the same directory as their `.iso`, with the same
basename.

Worth tuning on a many-core host — off by default:

```yaml
Multithreaded RSX: true
```

## Steam Deck specifics

- **No passwordless sudo.** Anything needing root is a manual step.
- **WiFi sleeps aggressively.** Long transfers drop; use `rsync --partial` with
  a retry loop rather than `scp`.
- **Immutable filesystem.** Install user-level binaries to `~/.local/bin` and
  user systemd units to `~/.config/systemd/user/`; never fight the read-only root.
- User services run only while logged in unless lingering is enabled — which
  needs root. In Game Mode you are always logged in, so this is usually moot.
