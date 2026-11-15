"""Cerca una foto per l'articolo e la salva in extra/img/articoli/<slug>.jpg.

Ordine: Pexels (se c'e' PEXELS_API_KEY) -> Openverse -> Wikimedia Commons (licenze libere, senza chiave).
Prova prima tutte le parole chiave, poi versioni piu' corte. Restituisce (percorso, credito).
"""
import html, json, os, re, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (sito-articoli; GitHub Actions)"}

def _get(url, headers=None, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or UA), timeout=timeout) as r:
        return r.read()

def _salva(img, slug):
    os.makedirs("extra/img/articoli", exist_ok=True)
    open(f"extra/img/articoli/{slug}.jpg", "wb").write(img)
    return f"/img/articoli/{slug}.jpg"

def _pexels(q, slug):
    pk = os.environ.get("PEXELS_API_KEY")
    if not pk:
        return None
    r = json.loads(_get(f"https://api.pexels.com/v1/search?query={urllib.parse.quote(q)}&per_page=5&orientation=landscape",
                        {"Authorization": pk, **UA}))
    for f in r.get("photos", []):
        return _salva(_get(f["src"]["large2x"]), slug), f"Foto: {f.get('photographer', 'Pexels')} / Pexels"
    return None

def _openverse(q, slug):
    r = json.loads(_get("https://api.openverse.org/v1/images/?q=" + urllib.parse.quote(q) +
                        "&license_type=commercial&aspect_ratio=wide&page_size=10"))
    for f in r.get("results", []):
        try:
            img = _get(f["url"])
            if len(img) < 30000:
                continue
            lic = (f.get("license") or "").upper()
            lic = lic if lic in ("CC0", "PDM") else "CC " + lic
            return _salva(img, slug), f"Foto: {f.get('title') or 'immagine'} di {f.get('creator') or 'autore sconosciuto'}, licenza {lic} {f.get('license_version') or ''}".strip()
        except Exception:
            continue
    return None

def _commons(q, slug):
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           "&gsrlimit=10&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=1600&gsrsearch=" +
           urllib.parse.quote(q + " filetype:bitmap"))
    pagine = json.loads(_get(url)).get("query", {}).get("pages", {})
    for p in sorted(pagine.values(), key=lambda x: x.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("width", 0) < 800 or ii.get("width", 0) < ii.get("height", 0):
            continue  # solo foto grandi e orizzontali
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not re.search(r"CC|Public domain|PD", lic, re.I) or re.search(r"NC|ND", lic):
            continue  # solo licenze che permettono uso commerciale e modifiche
        try:
            img = _get(ii.get("thumburl") or ii["url"])
            autore = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", ""))).strip() or "autore sconosciuto"
            titolo = p.get("title", "").replace("File:", "").rsplit(".", 1)[0]
            return _salva(img, slug), f"Foto: {titolo} di {autore[:80]}, {lic} (Wikimedia Commons)"
        except Exception:
            continue
    return None

def cerca_foto(parole, slug, riserva=""):
    parole = " ".join(str(parole or "").split())
    tentativi = []
    for q in (parole, " ".join(parole.split()[:2]), riserva):
        q = " ".join(str(q or "").split())
        if q and q not in tentativi:
            tentativi.append(q)
    for fonte in (_pexels, _openverse, _commons):
        for q in tentativi:
            try:
                ris = fonte(q, slug)
                if ris:
                    print(f"Foto trovata con {fonte.__name__[1:]} ('{q}')")
                    return ris
                print(f"Nessuna foto con {fonte.__name__[1:]} ('{q}')")
            except Exception as e:
                print(f"Errore {fonte.__name__[1:]} ('{q}'):", str(e)[:150])
    return "", ""
