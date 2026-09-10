# When `pacman -Syu` fails with 404s, suspect a bad mirror before the repos

A CachyOS upgrade failed repeatedly with what looked like missing packages. It
was two broken mirrors in a pool of thirty. Here is how to tell the difference,
because the symptoms are genuinely misleading.

## The symptom

```
error: failed retrieving file 'libgcc-...-x86_64_v3.pkg.tar.zst' from cdn77.cachyos.org : The requested URL returned error: 404
error: failed retrieving file 'kdesu-...-x86_64_v3.pkg.tar.zst.sig' from mirror5.krfoss.org : Maximum file size exceeded
warning: failed to retrieve some files
error: failed to commit transaction (failed to retrieve some files)
Errors occurred, no packages were upgraded.
```

**Each retry surfaced a *different* set of packages.** That is the tell. A genuine
upstream repo problem affects a stable set of packages; a bad mirror produces a
rotating cast, because pacman round-robins mirrors per file.

## The giveaway: `Maximum file size exceeded`

That error is **not** a missing package. It means the mirror returned something
pacman could not accept — an error page, a truncated response, a redirect to
something huge. A mirror doing that on `.sig` files will break any transaction
that happens to land on it, for any package.

Find which mirrors are misbehaving:

```bash
grep -oE "from [a-z0-9.-]+ :" /tmp/upgrade.log | sort | uniq -c | sort -rn
```

Then comment them out:

```bash
sudo cp /etc/pacman.d/cachyos-v3-mirrorlist{,.bak}
sudo sed -i '/badmirror\.example\.org/s/^Server/#Server/' /etc/pacman.d/cachyos-v3-mirrorlist
sudo sed -i '/badmirror\.example\.org/s/^Server/#Server/' /etc/pacman.d/cachyos-mirrorlist
sudo pacman -Sy
```

Removing two mirrors here fixed six of seven "missing" packages instantly.

## Two ways to fool yourself while diagnosing this

**1. `pacman -Sp` fails on dependencies, not availability.**

```bash
pacman -Sp libgcc      # "target not found" - looks missing
pacman -Sddp libgcc    # file:///var/cache/... - it was cached all along
```

`-Sp` performs full dependency resolution first. If anything in the tree is
unsatisfiable it errors out, which reads identically to the package being
absent. Use `-Sddp` to ask purely "where would this come from".

**2. Cached packages resolve to `file://`, not `https://`.**

A check like `pacman -Sp $pkg | grep -q '^https'` reports every cached package
as unavailable. Match both schemes:

```bash
pacman -Sddp "$pkg" | tail -1 | grep -qE '^(https|file)://'
```

Between them, these two mistakes had six perfectly good cached packages looking
like hard 404s.

## Check the local cache before chasing mirrors

Failed downloads often already exist locally from an earlier partial attempt:

```bash
ls /var/cache/pacman/pkg/${pkg}-*.pkg.tar.zst
zstd -t /var/cache/pacman/pkg/${pkg}-*.pkg.tar.zst   # verify not truncated
```

Note pacman needs the matching **`.sig`** too. A cached `.pkg.tar.zst` with no
`.sig` still triggers a download, and that is where a bad mirror bites.

## Verify your repo config is actually right

Worth ruling out before blaming anything upstream. Check the ISA level your CPU
genuinely supports:

```bash
/lib/ld-linux-x86-64.so.2 --help | grep -E 'x86-64-v[0-9]'
```

```
x86-64-v4
x86-64-v3 (supported, searched)
x86-64-v2 (supported, searched)
```

**Only lines marked `(supported, searched)` count.** A bare `x86-64-v4` means the
level is known but unsupported. Zen 2 (BC-250) has no AVX-512, so v3 is the
ceiling — `cachyos-v3` repos are correct, `cachyos-v4` would not be.

## Last resort, if the repos really are inconsistent

Temporarily comment out the three `cachyos-*-v3` repos in `/etc/pacman.conf` so
pacman pulls standard builds from `cachyos`/`core`/`extra`. They are only
x86-64-v3-optimised rebuilds — functionally identical, marginally slower. It
completes the upgrade in one pass and is reversible.

Try the mirror fix first. It is far less disruptive and, here, it was the actual
cause.

## Related: never use `pacman -Sy` to install a package

`-Sy` syncs the database without upgrading what is installed, so new packages get
built against a newer base than the system has. The visible symptom is obvious:

```
stress-ng: /usr/lib/libm.so.6: version `GLIBC_2.44' not found
```

The invisible one is worse. Here it left `vulkan-radeon` at 26.2.2 against
`mesa` 26.1.3, and that mismatch produced **amdgpu ring timeouts under DXVK** —
GPU hangs mid-game that looked like a hardware fault:

```
amdgpu: ring gfx_0.0.0 timeout, signaled seq=725448, emitted seq=725451
        Process GameThread pid 22305 thread dxvk-submit pid 22367
[drm] device wedged, but recovered through reset
```

Aligning both to 26.2.2 fixed it. Always `-Syu`, never `-Sy`.
