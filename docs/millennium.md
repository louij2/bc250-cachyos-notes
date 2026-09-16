# Porting CSS Loader themes to Millennium (Windows Big Picture)

The same Steam Deck themes that run on the BC-250 through Decky / CSS Loader can
run on a Windows PC's Big Picture Mode through
[Millennium](https://steambrew.app). The CSS mostly carries over. The packaging
does not, and one limit shapes the whole approach.

## Millennium allows one theme at a time

CSS Loader stacks as many themes as you enable. Millennium has a single
**active theme**, so two CSS Loader themes cannot simply be installed side by
side and both switched on. They have to be **merged into one skin**.

[`scripts/cssloader-to-millennium.py`](../scripts/cssloader-to-millennium.py)
does that merge.

## The converter

```bash
# copy the themes off the Deck/BC-250 first (quote the space)
scp -r "deck:homebrew/themes/Switch Like Home" "deck:homebrew/themes/Obsidian" ./themes/

python3 cssloader-to-millennium.py themes/Obsidian "themes/Switch Like Home" \
    -o ObsidianSwitchLikeHome --dry-run     # show the plan
python3 cssloader-to-millennium.py themes/Obsidian "themes/Switch Like Home" \
    -o ObsidianSwitchLikeHome               # write it
```

Output:

```
ObsidianSwitchLikeHome/
  skin.json                      one patch, MatchRegexString "Big Picture"
  vars.css                       option variables, loaded first
  Obsidian/shared.css            each theme namespaced in its own folder
  Obsidian/recents/monochrome.css
  Obsidian/other/no-blur.css
  Obsidian/other/no-glow.css
  Obsidian/LICENSE
  SwitchLikeHome/shared.css
  SwitchLikeHome/LICENSE
```

What it does:

- **Options.** Reads each theme's `config_USER.json`, i.e. the choices you
  made in CSS Loader, and bakes them in. A saved value can be a plain string or
  `{"value": ..., "components": {...}}`. A patch with no saved choice, or with a
  value the theme no longer offers, falls back to its `default` (with a
  warning).
- **Only used files.** Only the files that `inject` and the *selected* option
  values point at are copied, plus relative `url()` assets they reference and
  the theme's licence. The other 30-odd colour variants and `*.bak` files stay
  behind.
- **Variables.** Option `components` (colour pickers and the like) and the
  newer manifest-v9 inline form `"--var": ["value", "SP"]` become one
  generated `vars.css`, listed first. A component that belongs to the
  currently selected value (Obsidian's `Custom` colour) is written
  `!important`. Otherwise the theme's own `:root` default, which loads later,
  would silently win over your choice.
- **Targets.** CSS Loader's `SP`, `MainMenu` and `QuickAccess` are separate
  tabs on a Deck, but on desktop Big Picture they all render inside one
  window. They all map to the single patch. Anything else
  (`notificationtoasts.*`, `All`) is reported and dropped, not guessed.
- **Leftover old selectors.** `.module_ComponentName_hash` selectors that
  [`fix-css-themes.py`](css-themes.md) could not resolve are rewritten to
  `.ComponentName`. That would be pointless on a Deck. Millennium, though,
  rewrites Steam's class map from `Name:"hash"` to `Name:"hash Name"`, so
  every element also carries its readable component name as a class. On
  Obsidian that revives 22 dead selectors. Some still match nothing because
  the component is Deck-only (e.g. `RecentGamesBackgroundFadeGradient`) or
  only exists while a menu is open.
- **Namespacing.** Each theme's files go under `<ThemeName>/` (spaces
  stripped, since Millennium serves them by URL), so two themes' `shared.css`
  cannot collide.

Run it on the themes *after* `fix-css-themes.py`, so the hash-repaired CSS is
what gets ported.

## Installing

1. Copy the output folder to `C:\Program Files (x86)\Steam\millennium\themes\`.
2. Select it from Millennium's theme menu inside Steam. This applies live.

The active theme is also stored in
`millennium\config\config.json` → `themes.activeTheme` (the folder name), but
**only edit that file while Steam is fully closed**. Millennium rewrites it on
exit and will throw your edit away. It also falls back to `default` if the
named folder does not exist. Back it up first.

Do not run `steam.exe` from an SSH session to "restart" Steam, not even with
`-shutdown`. It starts a second, logged-out Steam in the SSH session instead
of talking to the one on the desktop.

## Layout themes and desktop resolutions

Colour themes port cleanly. **Layout** themes are the risk. Switch Like Home
sets `position: absolute` and `height: calc(100vh - ...)` on the home
carousel, with pixel constants measured on a 1280×800 Deck.

Measured on a 1930×941 Big Picture window:

| | stock | with Switch Like Home |
|---|---|---|
| carousel container | 54–454 px, 400 px tall | 54–843 px, 789 px tall |
| tile row | 310 px tall | absolute, bottom-anchored, 221 px tall |
| game title label | static, under tiles | absolute, above tiles |
| section tabs below | start at 424 px | start at 843 px |
| footer | 899–941 px | 899–941 px (unchanged) |
| carousel elements outside the viewport | 0 of 489 | 0 of 486 |

Because the heights are `vh`-based the layout scales. The carousel fills the
screen and stops above the footer, with nothing pushed off-screen and no zero
heights. That matches the theme's intent on a Deck. Re-check at unusual
aspect ratios (ultrawide, portrait) before trusting it there.

## Verifying it live

You can't see the result over SSH: the desktop session is a different
user. Steam's CEF debugger gets you there instead.

1. Enable the debugger. Create an empty file
   `C:\Program Files (x86)\Steam\.cef-enable-remote-debugging`, then restart
   Steam from the desktop. `http://127.0.0.1:8080/json` then lists the
   targets, including `SharedJSContext` and `Steam Big Picture Mode`.
2. Send `Runtime.evaluate` over the `SharedJSContext` websocket. On Windows
   PowerShell 5.1, `System.Net.WebSockets.ClientWebSocket` works; read until
   `EndOfMessage`. Load the JS with `[IO.File]::ReadAllText()`, not
   `Get-Content -Raw`. The latter returns a string with extra note
   properties, `ConvertTo-Json` serialises it as an object, and CDP rejects
   it with `string value expected`.
3. Get the Big Picture window:

   ```js
   const w = g_PopupManager.GetPopups()
     .find(p => p.m_strName === 'SP BPM_uid0').m_popup.window;
   ```

   From there, check:
   - `link[rel=stylesheet]` hrefs: the skin's files appear as
     `https://millennium.host/v1/themes/<Folder>/<file>`.
   - `querySelectorAll(sel).length` for selectors copied from your local CSS.
     You can't read `cssRules` itself: the sheets are cross-origin.
   - `getComputedStyle(...)`: for Obsidian, the home backgrounds and `#Footer`
     compute to `rgb(0, 0, 0)` and the recents strip to `rgb(255, 255, 255)`.
   - `fetch('https://millennium.host/v1/themes/<Folder>/skin.json')` returns
     200 once the folder is installed. This works even before the skin is
     selected.
4. **Test a layout theme before activating it.** In one synchronous
   evaluation, append its CSS as a `<style>`, force layout
   (`document.body.offsetHeight`), take `getBoundingClientRect()`
   measurements, and remove the `<style>` again. The browser never paints in
   between, so nothing flickers on the real screen. The table above was
   produced this way.
5. Delete the `.cef-enable-remote-debugging` marker afterwards. The debugger
   stays up until the next Steam restart, then goes away.
