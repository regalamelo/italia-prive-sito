#!/usr/bin/env python3
"""Costruisce il sito pubblicato da Cloudflare a partire dall'export Brizy.

1. Copia l'export Brizy (archivio di Brizy) in site/
2. Scarica i file JavaScript "preview.*.js" che Brizy non esporta
3. Aggiunge i file della cartella extra/ (robots.txt, llms.txt, articoli, ecc.)
"""
import os, re, shutil, sys, urllib.request

SRC, OUT, EXTRA = sys.argv[1], sys.argv[2], sys.argv[3]
LIVE = os.environ.get("BRIZY_LIVE_URL", "")
FREE_BASE = os.environ.get("BRIZY_FREE_BASE", "https://b-cloud.becdn.net/builds/free/385-cloud/editor/js/")
PRO_BASE = os.environ.get("BRIZY_PRO_BASE", "https://b-cloud.becdn.net/builds/pro/258-cloud/js/")
UA = {"User-Agent": "Mozilla/5.0 (brizy-sync)"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()

# 1. copia export
if os.path.exists(OUT):
    shutil.rmtree(OUT)
shutil.copytree(SRC, OUT, ignore=shutil.ignore_patterns(".git", ".github"))

# percorsi CDN aggiornati, letti dal sito Brizy Cloud (se indicato)
if LIVE:
    try:
        html = get(LIVE).decode("utf-8", "ignore")
        m = re.search(r"https://b-cloud\.becdn\.net/builds/free/[^/\"']+/editor/js/", html)
        if m: FREE_BASE = m.group(0)
        m = re.search(r"https://b-cloud\.becdn\.net/builds/pro/[^/\"']+/js/", html)
        if m: PRO_BASE = m.group(0)
    except Exception as e:
        print("Avviso: sito Brizy Cloud non leggibile:", e)
print("CDN free:", FREE_BASE, "\nCDN pro:", PRO_BASE)

# 2. file JS mancanti
assets = os.path.join(OUT, "assets")
pat = re.compile(r'"(preview(?:\.pro)?)\."\+(\w)\+"\."\+\(\{([^}]*)\}\)\[\2\]\+"\.js"')
chunks = set()
for f in os.listdir(assets):
    if f.endswith(".js"):
        txt = open(os.path.join(assets, f), encoding="utf-8", errors="ignore").read()
        for prefix, _, body in pat.findall(txt):
            for k, h in re.findall(r'(\d+):"([0-9a-f]+)"', body):
                chunks.add(f"{prefix}.{k}.{h}.js")
missing = []
for name in sorted(chunks):
    base = PRO_BASE if name.startswith("preview.pro.") else FREE_BASE
    try:
        data = get(base + name)
        if data.lstrip()[:1] == b"<":
            raise ValueError("ricevuto HTML")
        open(os.path.join(assets, name), "wb").write(data)
    except Exception as e:
        missing.append((name, base, e))
print(f"File JS scaricati: {len(chunks) - len(missing)}/{len(chunks)}")

redirects = os.path.join(OUT, "_redirects")
if missing:
    # piano B: rimanda i file non scaricati al CDN di Brizy
    with open(redirects, "a") as r:
        r.write("\n")
        for name, base, e in missing:
            print("NON scaricato:", name, e)
            r.write(f"/assets/{name}  {base}{name}  302\n")

# 3. file extra (sovrascrivono quelli di Brizy)
for root, _, files in os.walk(EXTRA):
    for f in files:
        if f == "LEGGIMI.md":
            continue
        src = os.path.join(root, f)
        rel = os.path.relpath(src, EXTRA)
        if rel == "_redirects_extra":
            with open(redirects, "a") as r:
                r.write("\n" + open(src).read())
            continue
        dst = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

if missing:
    print(f"::warning::{len(missing)} file JS non scaricati: usati i redirect verso il CDN di Brizy")
