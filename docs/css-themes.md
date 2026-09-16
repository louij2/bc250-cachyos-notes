# CSS Loader themes break after a Steam update — and it isn't the hashes

If your Decky / CSS Loader themes stop applying after Steam updates itself, the
usual advice is "re-download the themes, the class hashes changed". On the
2026-09-10 Steam client update that advice is wrong twice over, and the real
cause has a deterministic fix.

## The symptom

Every theme silently stops working. Nothing errors — CSS Loader reports the
themes as active, Decky is healthy, and the UI simply renders stock. If you run
layout themes the effect is more confusing, because the layout you are used to
disappears and it looks like something broke rather than something stopped.

Check whether your themes still target anything real:

```bash
grep -rhoE '\.[a-z]+_[A-Za-z]+_[A-Za-z0-9]{4,8}' ~/homebrew/themes/*/*.css \
  | sed 's/^\.//' | sort -u | while read -r c; do
    grep -rq "$c" ~/.local/share/Steam/steamui/ || echo "dead: $c"
  done | head
```

A wall of `dead:` lines means the selectors no longer match anything.

## Why re-downloading does not help

Check what upstream actually has. The DeckThemes API needs a non-default
user-agent or it returns 403:

```bash
ID=$(python3 -c "import json;print(json.load(open('THEME/theme.json'))['id'])")
curl -s -A 'Mozilla/5.0' "https://api.deckthemes.com/themes/$ID" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["version"], d["updated"][:10])'
```

On the machine this was written from, **all 22 active themes were already at the
newest published version**, and most were last updated in 2023 or 2024. Steam
Deck theming has quietened down; many popular themes are effectively abandoned.
There is nothing newer to download.

## The actual cause: the class-name *format* changed

Steam did not re-roll its CSS module hashes. It changed how it emits them.

```
before:  .gamepadhomerecentgames_RecentGamesInnerContainer_282X0
after:   ._282X0J4BtrSF1IXctmOe-X
```

The old readable name carried a **truncated** hash on the end. The new class is
the **full** hash with the readable part dropped. The `282X0` in the old
selector is the first five characters of the new one.

That means the old selector contains enough information to recover the new one,
and Steam's own JS bundle contains the authoritative mapping:

```bash
grep -ohE 'RecentGamesInnerContainer\s*:\s*"[^"]+"' ~/.local/share/Steam/steamui/*.js
# RecentGamesInnerContainer:"_282X0J4BtrSF1IXctmOe-X"
```

Two gotchas when harvesting those pairs:

- Some hashes start with `_`, some do not (`"cE1SaW6jrVUDxcqRtyMo1"` vs
  `"_131Hc_PylzRH3dEQlTP4mY"`). A regex that assumes a leading underscore
  silently misses about a fifth of them.
- A component name can map to several hashes. The truncated hash in the old
  selector disambiguates them — match on it first, and only fall back to the
  name when it maps to exactly one hash.

## The fix

[`scripts/fix-css-themes.py`](../scripts/fix-css-themes.py) reads Steam's
current bundle, builds the `ComponentName → hash` map, and re-points every
theme's selectors at the live classes. It tars the whole themes directory
first and writes a `.pre-hashfix.bak` beside every file it edits.

```bash
python3 fix-css-themes.py
# restart Steam (or the gamescope session) to apply
```

Result on the reference machine: **0% → 80%** of theme selectors matching live
Steam classes, 1306 rules rewritten across 21 themes.

### Two bugs fixed after the first release

- **Option subfolders were skipped.** Themes keep their colour and option CSS
  in subfolders (`colors/`, `recents/`, `other/`). The first version only
  globbed one level deep, so on the reference machine 42 of 96 option files
  were never repaired — every colour choice silently did nothing. The script
  now recurses; a re-run rewrote 198 more rules and left 5 files that only
  reference components Steam removed.
- **Re-running overwrote the backups.** Each run wrote `.pre-hashfix.bak`
  unconditionally, so a second run replaced the original CSS with
  already-rewritten CSS. It now keeps the first original only. If you ran the
  old version twice, restore from the `themes-backup-*.tar.gz` it also writes.

### On Windows with Millennium

Millennium (the Windows equivalent of Decky/CSS Loader) rewrites Steam's class
map from `Name:"hash"` to `Name:"hash Name"` — elements keep the hash **and**
gain the readable component name as an extra class. So selectors re-pointed by
this script still match under Millennium. Millennium uses `skin.json` rather
than CSS Loader's `theme.json`, and matches patches against the window title or
classes; desktop Big Picture's window title is `Steam Big Picture Mode`.

### What it deliberately does not do

The remaining ~20% are components Steam genuinely renamed or removed, where the
name maps to several hashes and no truncated hash survives to disambiguate.
Guessing there would produce rules that match the wrong element, which is worse
than a rule that matches nothing. Those are left dead.

Rewriting is safe in the sense that it cannot regress anything: an unresolved
selector stays exactly as dead as it already was. But a theme that comes back
only *partially* can look worse than one that is fully off — check anything
reporting a low match rate and toggle it off if it looks half-applied.

### This will recur

Every Steam client update that changes the UI bundle breaks these themes again,
and while the upstream themes stay unmaintained, re-running the script is the
maintenance. It is idempotent and backs up each time.

## Related: themes re-enabling themselves across machines

If you sync `~/homebrew` between machines, note that CSS Loader stores each
theme's enabled state in that theme's `config_USER.json`, not in
`homebrew/settings/`. Syncing it will re-enable themes on a machine whose screen
resolution they were never designed for. Exclude it:

```
# ~/homebrew/themes/.stignore
config_USER.json
```
