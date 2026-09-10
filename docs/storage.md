# Portable games/media storage — one btrfs pool, no fixed split

A console-style box that travels usually ends up with an external drive holding
three things that grow unpredictably: Steam games, media for a local Plex, and
emulator ROMs. The obvious approach — partition it into fixed slices — is the
one you will regret.

## Don't use fixed partitions

Two ext4 partitions of 1 TB each looks tidy and then media outgrows its half
while games sit on 400 GB of unused space. Fixing that means unmounting,
`resize2fs`, moving partition boundaries, and hoping. On a USB drive with a
sleepy bridge chip that is not a pleasant afternoon.

## Use btrfs subvolumes instead

One filesystem across the whole disk, subvolumes mounted separately. They share
free space dynamically — there is no allocation to change.

```bash
sudo wipefs -a /dev/sdX
sudo parted -s /dev/sdX mklabel gpt
sudo parted -s /dev/sdX mkpart storage btrfs 1MiB 100%
sudo partprobe /dev/sdX; sleep 3
sudo mkfs.btrfs -f -L mystore /dev/sdX1

sudo mkdir -p /mnt/store && sudo mount -t btrfs /dev/sdX1 /mnt/store
for sv in games media roms; do sudo btrfs subvolume create /mnt/store/@$sv; done
sudo umount /mnt/store
```

Then in `/etc/fstab`, one line per subvolume, all the same UUID:

```
UUID=<uuid> /mnt/games btrfs subvol=@games,defaults,nofail,compress=zstd:3,x-systemd.device-timeout=10 0 0
UUID=<uuid> /mnt/media btrfs subvol=@media,defaults,nofail,compress=zstd:3,x-systemd.device-timeout=10 0 0
UUID=<uuid> /mnt/roms  btrfs subvol=@roms,defaults,nofail,compress=zstd:3,x-systemd.device-timeout=10 0 0
```

`df` then reports the same free space against all three, because that is the
truth — they draw from one pool.

### Why each mount option

- **`nofail`** — essential on a removable drive. Without it the machine drops to
  an emergency shell at boot when the drive isn't plugged in.
- **`x-systemd.device-timeout=10`** — caps how long boot waits for a missing
  drive. Without it you wait 90 s.
- **`compress=zstd:3`** — free space on game assets and save data. btrfs detects
  incompressible data and skips it, so video costs nothing.
- **UUID, not `/dev/sdX`** — USB device names move between boots.

If you later want hard limits after all, btrfs quotas can impose them without
repartitioning:

```bash
sudo btrfs quota enable /mnt/games
sudo btrfs qgroup limit 800G /mnt/media
```

## Two gotchas worth knowing

**Mount immediately after mkfs can fail with the *old* filesystem type.** blkid
caches, so `mount` may try ext4 on a freshly-made btrfs and fail with
"wrong fs type, bad option, bad superblock". `dmesg` gives it away:

```
EXT4-fs (sda1): VFS: Can't find ext4 filesystem
```

Not a real failure. Pass `-t btrfs` explicitly, or wait for the cache to settle.

**USB drives sleeping or dropping off.** Disable both USB autosuspend and the
bridge's APM spindown:

```bash
# udev rule, replace with your bridge's vendor id from lsusb
printf 'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1058", ATTR{power/control}="on"\n' \
  | sudo tee /etc/udev/rules.d/50-usb-hdd-nosuspend.rules
sudo udevadm control --reload
sudo hdparm -B 255 -S 0 /dev/sdX
```

## Pointing EmuDeck at it

EmuDeck expects `~/Emulation`. Symlink it so ROMs land on the external drive
instead of the system SSD:

```bash
ln -sfn /mnt/roms ~/Emulation
```

Create the tree first and EmuDeck adopts it rather than building its own. To
mirror an existing Steam Deck exactly, copy the folder names across:

```bash
ssh deck@steamdeck 'ls -1 ~/Emulation/roms/' > /tmp/romsystems.txt
mkdir -p /mnt/roms/{bios,hdpacks,roms,saves,storage,texturepacks,tools}
cd /mnt/roms/roms && while read -r s; do [ -n "$s" ] && mkdir -p "$s"; done < /tmp/romsystems.txt
```

A stock EmuDeck install has around 228 system folders.

### Steam ROM Manager will kill your UI if you let it

It creates one Steam shortcut **and one grid image** per ROM. Steam's library UI
degrades badly in the low thousands and becomes unusable well before 30,000.

Parse only the systems you actually play, and keep the total in the low
hundreds. The offenders are the big 8-bit and handheld sets — a complete NES or
GBA collection is thousands of entries by itself. You can always run it again to
add more; recovering from a wedged library is far more tedious.
