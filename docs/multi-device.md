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

## Mounting a NAS share on both machines

Two working patterns, for an SMB share holding ROMs and a Steam library.

### SMB does not listen on the Tailscale address

The obvious idea — point the mount at the NAS's Tailscale IP so it works from
anywhere — **does not work**. Most NAS SMB services bind to the LAN interface
only:

```
<nas-tailscale-ip>  port 445: CLOSED
<nas-lan-ip>        port 445: OPEN
```

The mount fails with:

```
mount error(111): could not connect to <ip> Unable to find suitable address.
CIFS: VFS: Error connecting to socket. Aborting operation.
```

**Use the LAN IP and reach it through a Tailscale subnet route.** The NAS
advertises its LAN subnet; roaming clients pick it up and the LAN address stays
valid from anywhere.

### Do not enable `--accept-routes` on a client already on that subnet

If the client lives on the same LAN as the NAS, accepting a route for that same
subnet is redundant at best and disruptive at worst — it can break local
connectivity mid-flight, including the SSH session you are working over.

Only roaming clients need `--accept-routes`.

### Pattern A — script (Steam Deck / SteamOS)

Useful where you want an explicit fallback and a machine that is often asleep.

```bash
SERVER="<nas-lan-ip>"
declare -A MOUNTS=(
    ["/mnt/games"]="//<nas-lan-ip>/Games/"
    ["/mnt/steamnas"]="//<nas-lan-ip>/Games/SteamLibrary"
)

# clear stale handles first - 'timeout' stops the script hanging on a dead mount
for MP in "${!MOUNTS[@]}"; do
    [ ! -d "$MP" ] && sudo mkdir -p "$MP"
    timeout 2 ls "$MP" &>/dev/null || sudo umount -l "$MP" 2>/dev/null || true
done

# fall back to Tailscale if the NAS is not reachable locally
if ! timeout 3 ping -c 1 "$SERVER" &>/dev/null; then
    sudo tailscale up --accept-routes --accept-dns=false || true
    sleep 5
fi

for MP in "${!MOUNTS[@]}"; do
    mountpoint -q "$MP" && continue
    timeout 15 sudo mount -t cifs "${MOUNTS[$MP]}" "$MP" \
      -o credentials=/path/to/creds,uid=1000,gid=1000,iocharset=utf8,vers=3.1.1,\
file_mode=0777,dir_mode=0777,mfsymlinks,nobrl,soft,retrans=2,_netdev
done
```

### Pattern B — systemd automount (preferred for an always-on host)

Mounts on first access, unmounts when idle, retries by itself, and **never
blocks boot** when the NAS is unreachable. Better for a machine that travels.

`/etc/systemd/system/mnt-nas\x2dgames.mount` — note systemd escapes `-` in unit
filenames as `\x2d`:

```ini
[Unit]
Description=NAS Games share
After=network-online.target tailscaled.service
Wants=network-online.target

[Mount]
What=//<nas-lan-ip>/Games
Where=/mnt/nas-games
Type=cifs
Options=credentials=/etc/samba/creds-nas,uid=1000,gid=1000,iocharset=utf8,vers=3.1.1,file_mode=0777,dir_mode=0777,mfsymlinks,nobrl,soft,retrans=2,_netdev,x-systemd.automount,x-systemd.idle-timeout=600,x-systemd.mount-timeout=15
TimeoutSec=20

[Install]
WantedBy=multi-user.target
```

With a matching `.automount`:

```ini
[Unit]
Description=Automount for /mnt/nas-games
[Automount]
Where=/mnt/nas-games
TimeoutIdleSec=600
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now 'mnt-nas\x2dgames.automount'
```

### The mount options that matter

Copied from a setup tuned for Steam over SMB, and each earns its place:

- **`mfsymlinks`** — lets Proton and Steam create symlinks on a share that has
  no native symlink support. Without it, game installs fail in odd ways.
- **`nobrl`** — disables byte-range locking. Fixes downloads that hang at
  0 bytes.
- **`file_mode=0777,dir_mode=0777`** — SMB carries no usable POSIX permissions;
  without these Steam cannot write.
- **`soft,retrans=2`** — fail rather than block forever when the NAS vanishes.
  Prevents the whole UI freezing on a dropped connection.
- **`_netdev`** — do not try to mount before the network exists.

### Watch the mount point names

If the host already has local storage mounted at `/mnt/games`, a NAS share
cannot also mount there — the unit fails with `No such device` and the cause is
not obvious from the error. Give the NAS its own path (`/mnt/nas-games`) and
keep local and remote clearly distinct.

### Credentials

Keep them in a root-owned file, mode `600`, referenced by `credentials=`:

```
username=<user>
password=<pass>
```

Never inline a password in a unit file or fstab entry - those are world-readable.
