#!/usr/bin/env python3
"""Salva in articoli/ un articolo ricevuto da Albato / n8n (repository_dispatch).

Dati attesi in client_payload:
  titolo (obbligatorio), testo (obbligatorio), descrizione, categoria, immagine, data, slug,
  parole_chiave_foto (in inglese: se manca l'immagine si cerca una foto libera su Openverse)
Il testo puo' essere semplice (paragrafi separati da a capo) o HTML (<p>...</p>).
"""
import datetime, html, json, os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto import cerca_foto

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

# righe iniziali scritte dal Gem (Titolo:, Descrizione:, Categoria:, Foto:, ---) -> dati dell'articolo
CAMPI = {"titolo": "titolo", "descrizione": "descrizione", "categoria": "categoria", "foto": "parole_chiave_foto"}
_par = pulisci(testo).split("\n\n")
while _par:
    m = re.match(r"^[*#\s]*(titolo|descrizione|categoria|foto)[*\s]*:[*\s]*(.*?)[*\s]*$", _par[0], re.I)
    if m:
        chiave = CAMPI[m.group(1).lower()]
        if m.group(2) and (chiave != "titolo" or not d.get("titolo")):
            d[chiave] = m.group(2)
        _par.pop(0)
    elif re.fullmatch(r"[-_*\s]{3,}", _par[0]):
        _par.pop(0)
    else:
        break
testo = "\n\n".join(_par)

slug = slugify(d.get("slug") or titolo)
from zoneinfo import ZoneInfo
data = una_riga(d.get("data")) or datetime.datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="seconds")
meta = {
    "titolo": una_riga(titolo),
    "descrizione": una_riga(d.get("descrizione")),
    "categoria": una_riga(d.get("categoria")).lower(),
    "immagine": una_riga(d.get("immagine")),
    "data": data,
}
corpo = pulisci(testo)
if not meta["immagine"]:
    meta["immagine"], credito = cerca_foto(una_riga(d.get("parole_chiave_foto")), slug, titolo)
    if credito:
        corpo += "\n\n" + credito
righe = ["---"] + [f"{k}: {v}" for k, v in meta.items() if v] + ["---", corpo, ""]
os.makedirs("articoli", exist_ok=True)
path = os.path.join("articoli", slug + ".md")
open(path, "w", encoding="utf-8").write("\n".join(righe))
print("Articolo salvato:", path)
if os.environ.get("GITHUB_OUTPUT"):
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"slug={slug}\n")
