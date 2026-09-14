#!/usr/bin/env python3
"""Re-point CSS Loader theme selectors at Steam's current class hashes.
Re-run after any Steam client update. Backs up to themes-backup-<ts>.tar.gz"""
import re, os, glob, collections, subprocess, time, sys
U=os.path.expanduser('~/.local/share/Steam/steamui')
T=os.path.expanduser('~/homebrew/themes')

ts=time.strftime('%Y%m%d-%H%M%S')
bk=os.path.expanduser('~/themes-backup-%s.tar.gz'%ts)
subprocess.run(['tar','czf',bk,'-C',os.path.dirname(T),os.path.basename(T)],check=True)
print("  backup: %s (%.1f MB)" % (bk, os.path.getsize(bk)/1e6))

pair=re.compile(r'([A-Za-z][A-Za-z0-9]{2,60})\s*:\s*"(_?[A-Za-z0-9][A-Za-z0-9_\-]{12,40})"')
m=collections.defaultdict(set)
for f in glob.glob(U+'/*.js'):
    try: s=open(f,errors='ignore').read()
    except Exception: continue
    for n,h in pair.findall(s): m[n].add(h)
print("  mapped %d component names from Steam bundle" % len(m))

sel=re.compile(r'\.([a-zA-Z0-9]+)_([A-Za-z0-9]+)_([A-Za-z0-9\-]{4,10})\b')
def resolve(name,short):
    hs=m.get(name,())
    c=[h for h in hs if h.lstrip('_').startswith(short.lstrip('_'))]
    if len(c)>=1: return sorted(c)[0]
    if len(hs)==1: return list(hs)[0]
    return None

tot=chg=0; per=collections.Counter()
for css in sorted(glob.glob(T+'/*/*.css')):
    theme=css.split('/')[-2]
    try: s=open(css,errors='ignore').read()
    except Exception: continue
    orig=s
    def sub(mo):
        global tot,chg
        tot+=1
        h=resolve(mo.group(2),mo.group(3))
        if h:
            chg+=1; per[theme]+=1
            return '.'+h
        return mo.group(0)
    s=sel.sub(sub,s)
    if s!=orig:
        open(css+'.pre-hashfix.bak','w').write(orig)
        open(css,'w').write(s)
print("  selectors seen: %d   rewritten: %d" % (tot,chg))
for t,c in per.most_common(): print("    %-34s %d rules" % (t[:34],c))
print("  DONE - restart Steam to apply")
