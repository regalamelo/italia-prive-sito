#!/usr/bin/env python3
"""Salva in articoli/ un articolo ricevuto da Albato / n8n (repository_dispatch).

Dati attesi in client_payload:
  titolo (obbligatorio), testo (obbligatorio), descrizione, categoria, immagine, data, slug,
  parole_chiave_foto (in inglese: se manca l'immagine si cerca una foto libera su Openverse)
Il testo puo' essere semplice (paragrafi separati da a capo) o HTML (<p>...</p>).
"""
import datetime, html, json, os, re, sys, unicodedata, urllib.parse, urllib.request

d = json.loads(os.environ.get("PAYLOAD") or "{}")
titolo = (d.get("titolo") or "").strip()
testo = (d.get("testo") or "").strip()
if not titolo or not testo:
    sys.exit("ERRORE: servono almeno 'titolo' e 'testo'")

def slugify(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:80] or "articolo"

def pulisci(t):
    t = t.replace("\r\n", "\n")
    if "<" in t:  # HTML -> testo
        t = re.sub(r"(?i)<\s*(strong|b)\s*>(.*?)<\s*/\s*\1\s*>", r"**\2**", t, flags=re.S)
        t = re.sub(r"(?i)<\s*br\s*/?>", "\n", t)
        t = re.sub(r"(?i)</\s*(p|div|h[1-6]|li)\s*>", "\n\n", t)
        t = re.sub(r"<[^>]+>", "", t)
        t = html.unescape(t)
    righe = [r.strip() for r in t.split("\n")]
    return "\n\n".join(r for r in righe if r)  # ogni riga = un paragrafo

def una_riga(v):
    return " ".join(str(v or "").split())

def foto_openverse(parole, slug):
    """Se manca l'immagine: foto con licenza libera per uso commerciale (Openverse, senza chiave)."""
    ua = {"User-Agent": "Mozilla/5.0 (sito-articoli)"}
    q = urllib.parse.quote(parole)
    url = f"https://api.openverse.org/v1/images/?q={q}&license_type=commercial&aspect_ratio=wide&size=large&page_size=10"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=60) as r:
            risultati = json.loads(r.read()).get("results", [])
    except Exception as e:
        print("Ricerca foto non riuscita:", e)
        return "", ""
    for f in risultati:
        try:
            with urllib.request.urlopen(urllib.request.Request(f["url"], headers=ua), timeout=60) as r:
                img = r.read()
            if len(img) < 20000:
                continue
            os.makedirs("extra/img/articoli", exist_ok=True)
            open(f"extra/img/articoli/{slug}.jpg", "wb").write(img)
            lic = (f.get("license") or "").upper()
            credito = f"Foto: {f.get('title') or 'immagine'} di {f.get('creator') or 'autore sconosciuto'}, licenza {lic if lic in ('CC0', 'PDM') else 'CC ' + lic} {f.get('license_version') or ''}".strip()
            print("Foto:", f.get("foreign_landing_url"))
            return f"/img/articoli/{slug}.jpg", credito
        except Exception:
            continue
    return "", ""

slug = slugify(d.get("slug") or titolo)
data = una_riga(d.get("data")) or datetime.date.today().isoformat()
meta = {
    "titolo": una_riga(titolo),
    "descrizione": una_riga(d.get("descrizione")),
    "categoria": una_riga(d.get("categoria")).lower(),
    "immagine": una_riga(d.get("immagine")),
    "data": data[:10],
}
corpo = pulisci(testo)
if not meta["immagine"]:
    meta["immagine"], credito = foto_openverse(una_riga(d.get("parole_chiave_foto")) or titolo, slug)
    if credito:
        corpo += "\n\n" + credito
righe = ["---"] + [f"{k}: {v}" for k, v in meta.items() if v] + ["---", corpo, ""]
os.makedirs("articoli", exist_ok=True)
path = os.path.join("articoli", slug + ".md")
open(path, "w", encoding="utf-8").write("\n".join(righe))
print("Articolo salvato:", path)
if os.environ.get("GITHUB_OUTPUT"):
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"slug={slug}\n")
