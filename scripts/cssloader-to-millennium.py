#!/usr/bin/env python3
"""Convert one or more CSS Loader (Decky) themes into a single Millennium skin.

Millennium (Windows Steam theming) allows only ONE active theme, so every input
theme is merged into one skin directory:

    OUT/skin.json          Millennium manifest, one patch for Big Picture
    OUT/vars.css           CSS variables from options, loaded first
    OUT/<Theme>/<file>.css only the files the chosen options actually use

For each theme it reads theme.json and, if present, config_USER.json (the
options you picked in CSS Loader). A patch with no saved choice, or a saved
choice the theme no longer offers, falls back to the patch's "default".

CSS Loader targets SP, MainMenu and QuickAccess are separate tabs on a Deck.
On desktop Big Picture they all render inside one window, so they map to one
Millennium patch. Any other target (notificationtoasts.*, All, ...) is reported
and dropped rather than guessed at.

Usage:
    cssloader-to-millennium.py THEME_DIR [THEME_DIR ...] -o OUT_DIR
        [--name NAME] [--match 'Big Picture'] [--dry-run] [--force]

Python 3 stdlib only.
"""
import argparse, json, os, re, shutil, sys

# CSS Loader tab names that live inside desktop Big Picture's single window.
BPM_TARGETS = {'SP', 'MainMenu', 'QuickAccess'}

# Old-format Steam class: .<module>_<ComponentName>_<shorthash>
# Steam stopped emitting these; fix-css-themes.py re-points the ones it can
# resolve, and the rest are left behind. Millennium rewrites Steam's module map
# from Name:"hash" to Name:"hash Name", so every element also carries its bare
# component name as a class. Rewriting a leftover to .<ComponentName> therefore
# brings it back to life under Millennium (it would stay dead on a Deck).
OLD_SEL = re.compile(r'\.([a-zA-Z0-9]+)_([A-Za-z0-9]+)_([A-Za-z0-9\-]{4,10})\b')
URL_REF = re.compile(r'''url\(\s*['"]?([^'")]+?)['"]?\s*\)''')

warnings = []


def warn(msg):
    warnings.append(msg)
    print('  WARN: ' + msg, file=sys.stderr)


def slug(name):
    """Folder-safe namespace: Millennium serves files by URL, avoid spaces."""
    s = re.sub(r'[^A-Za-z0-9_-]+', '', name)
    return s or 'theme'


def rewrite_old(css):
    n = 0

    def sub(mo):
        nonlocal n
        # module part of the old format is always lowercase ("gamepaddialog");
        # this guard keeps a real full hash containing '_' from being mangled
        if not mo.group(1).islower():
            return mo.group(0)
        n += 1
        return '.' + mo.group(2)
    return OLD_SEL.sub(sub, css), n


def split_targets(theme, what, targets):
    bad = [t for t in targets if t not in BPM_TARGETS]
    for t in bad:
        warn('%s: %s targets "%s" - no Millennium equivalent, dropped' % (theme, what, t))
    return any(t in BPM_TARGETS for t in targets)


def load_theme(tdir):
    """Return (meta, ordered css files, vars dict) for one theme dir."""
    with open(os.path.join(tdir, 'theme.json')) as f:
        tj = json.load(f)
    name = tj.get('name') or os.path.basename(os.path.normpath(tdir))
    cfg = {}
    cp = os.path.join(tdir, 'config_USER.json')
    if os.path.exists(cp):
        with open(cp) as f:
            cfg = json.load(f)
    files, vars_, chosen = [], {}, {}

    def take(entries):
        for key, val in entries.items():
            if key.startswith('--'):
                # manifest v9 inline variable: "--var": [value, target, ...]
                if split_targets(name, key, val[1:]):
                    vars_[key] = (val[0], False)
            elif split_targets(name, key, val):
                if key not in files:
                    files.append(key)

    take(tj.get('inject', {}))
    for pname, patch in tj.get('patches', {}).items():
        saved = cfg.get(pname)
        comp_saved = {}
        if isinstance(saved, dict):
            comp_saved = saved.get('components', {}) or {}
            saved = saved.get('value')
        values = patch.get('values', {})
        sel = saved if saved is not None else patch.get('default')
        if sel not in values:
            if saved is not None:
                warn('%s: "%s" = "%s" is not an option, using default "%s"'
                     % (name, pname, saved, patch.get('default')))
            sel = patch.get('default')
        chosen[pname] = sel
        take(values.get(sel, {}))
        for c in patch.get('components', []):
            var = c.get('css_variable')
            if not var:
                continue
            v = comp_saved.get(c.get('name'), c.get('default'))
            if v is None:
                continue
            # A component that belongs to the selected value (e.g. "Custom")
            # must beat the theme's own :root default, which loads after
            # vars.css - so mark it !important. Otherwise emit it plain, so
            # a selected colour file can still override it.
            vars_[var] = (v, c.get('on') is not None and c.get('on') == sel)
    meta = {'name': name, 'author': tj.get('author', ''),
            'version': str(tj.get('version', '')).lstrip('v'), 'chosen': chosen}
    return meta, files, vars_


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('themes', nargs='+', help='CSS Loader theme directories')
    ap.add_argument('-o', '--out', required=True, help='output skin directory')
    ap.add_argument('--name', help='skin name (default: theme names joined)')
    ap.add_argument('--match', default='Big Picture',
                    help='Millennium MatchRegexString (default: %(default)s)')
    ap.add_argument('--dry-run', action='store_true', help='show the plan, write nothing')
    ap.add_argument('--force', action='store_true', help='replace an existing OUT dir')
    a = ap.parse_args()

    plan, targets, var_blocks, used_ns = [], ['vars.css'], [], set()
    metas = []
    for tdir in a.themes:
        meta, files, vars_ = load_theme(tdir)
        ns = slug(meta['name'])
        while ns in used_ns:
            ns += '_'
        used_ns.add(ns)
        metas.append(meta)
        print('%s -> %s/' % (meta['name'], ns))
        for p, v in meta['chosen'].items():
            print('    %-28s %s' % (p, v))
        # licence travels with the CSS it covers (not loaded, just kept)
        queue = list(files) + sorted(f for f in os.listdir(tdir)
                                     if f.upper().startswith(('LICENSE', 'LICENCE', 'COPYING')))
        seen = set()
        while queue:
            rel = queue.pop(0)
            if rel in seen or rel.endswith('.bak'):
                continue
            seen.add(rel)
            src = os.path.join(tdir, rel)
            if not os.path.isfile(src):
                warn('%s: %s is referenced but missing' % (meta['name'], rel))
                continue
            dst = ns + '/' + rel.replace(os.sep, '/')
            if rel.endswith('.css'):
                with open(src, errors='ignore') as f:
                    css, n = rewrite_old(f.read())
                # pull in relative assets (images, fonts) the CSS points at
                for u in URL_REF.findall(css):
                    if not re.match(r'^(data:|https?:|/|#|var\()', u):
                        queue.append(os.path.normpath(os.path.join(os.path.dirname(rel), u)))
                if rel in files:
                    targets.append(dst)
                plan.append((dst, css, None))
                print('    + %-40s %s' % (dst, ('%d old selectors -> .Name' % n) if n else ''))
            else:
                plan.append((dst, None, src))
                print('    + %s (asset)' % dst)
        if vars_:
            lines = ['  %s: %s%s;' % (k, v, ' !important' if imp else '')
                     for k, (v, imp) in vars_.items()]
            var_blocks.append('/* %s */\n:root {\n%s\n}\n' % (meta['name'], '\n'.join(lines)))

    vars_css = ('/* Generated by cssloader-to-millennium.py from option values\n'
                '   (your config_USER.json choices, else defaults). Loaded first. */\n'
                + '\n'.join(var_blocks))
    names = [m['name'] for m in metas]
    skin = {
        'name': a.name or ' + '.join(names),
        'version': '+'.join(m['version'] for m in metas),
        'author': ', '.join(dict.fromkeys(m['author'] for m in metas if m['author'])),
        'description': 'Merged from CSS Loader themes %s by cssloader-to-millennium.py. '
                       'Options: %s.' % (', '.join(names), '; '.join(
                           '%s: %s' % (m['name'], ', '.join('%s=%s' % kv for kv in m['chosen'].items()))
                           for m in metas)),
        'Patches': [{'MatchRegexString': a.match, 'TargetCss': targets}],
    }
    print('\nskin.json TargetCss (load order):')
    for t in targets:
        print('    ' + t)
    print('%d files + skin.json, %d warnings' % (len(plan) + 1, len(warnings)))
    if a.dry_run:
        print('dry run - nothing written')
        return

    if os.path.exists(a.out) and os.listdir(a.out):
        if not a.force:
            sys.exit('%s exists and is not empty (use --force to replace it)' % a.out)
        shutil.rmtree(a.out)
    os.makedirs(a.out, exist_ok=True)
    for dst, css, src in plan:
        p = os.path.join(a.out, dst)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if css is not None:
            with open(p, 'w') as f:
                f.write(css)
        else:
            shutil.copyfile(src, p)
    with open(os.path.join(a.out, 'vars.css'), 'w') as f:
        f.write(vars_css)
    with open(os.path.join(a.out, 'skin.json'), 'w') as f:
        json.dump(skin, f, indent=2)
        f.write('\n')
    print('wrote %s' % a.out)


if __name__ == '__main__':
    main()
