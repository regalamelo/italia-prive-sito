#!/usr/bin/env python3
"""Cambia la foto di un articolo già pubblicato (richiesta da WhatsApp -> Albato -> GitHub).

Uso: ARTICOLO="titolo o argomento (vuoto = ultimo pubblicato)" FOTO="cosa deve mostrare la foto" python3 scripts/cambia_foto.py
Segreti facoltativi: UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, GROQ_API_KEY / GEMINI_API_KEY (per tradurre la richiesta in parole chiave inglesi)
"""
import json, os, re, sys, unicodedata, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import foto

CARTELLA = "articoli"
ARTICOLO = " ".join((os.environ.get("ARTICOLO") or "").split())
RICHIESTA = " ".join((os.environ.get("FOTO") or "").split())
for v in (ARTICOLO, RICHIESTA):
    if "{%" in v or "%}" in v:
        sys.exit("ERRORE: variabile Albato non sostituita: " + v)

def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", t)

def leggi(nome):
    raw = open(os.path.join(CARTELLA, nome), encoding="utf-8").read()
    meta = {}
    m = re.match(r"---\n(.*?)\n---\n", raw, re.S)
    if m:
        for riga in m.group(1).splitlines():
            if ":" in riga:
                k, v = riga.split(":", 1)
                meta[k.strip().lower()] = v.strip()
    return raw, meta

# ---------- quale articolo ----------
articoli = []
for nome in os.listdir(CARTELLA):
    if nome.endswith(".md") and not nome.startswith("_"):
        raw, meta = leggi(nome)
        articoli.append((nome, raw, meta))
if not articoli:
    sys.exit("ERRORE: nessun articolo")

def punteggio(a):
    nome, _, meta = a
    testo = set(norm(nome[:-3].replace("-", " ") + " " + meta.get("titolo", "") + " " + meta.get("argomento", "")))
    chiavi = [w for w in norm(ARTICOLO) if len(w) > 3]
    return sum(1 for w in chiavi if w in testo)

recenti = sorted(articoli, key=lambda a: a[2].get("data", ""), reverse=True)
scelto = recenti[0]
if ARTICOLO:
    migliore = max(recenti, key=punteggio)  # a parità vince il più recente
    if punteggio(migliore) > 0:
        scelto = migliore
nome, raw, meta = scelto
print("Articolo:", nome)

# ---------- parole chiave della foto (in inglese, per gli archivi foto) ----------
base = RICHIESTA or meta.get("titolo", "") or nome[:-3].replace("-", " ")

def http(url, data=None, headers=None, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers or {}), timeout=timeout) as r:
        return r.read()

def parole_inglesi(testo):
    domanda = ("Trasforma questa richiesta di foto in 2-4 parole chiave INGLESI per cercare una foto su Unsplash. "
               "Rispondi solo con le parole, senza punteggiatura.\nRichiesta: " + testo)
    groq = os.environ.get("GROQ_API_KEY")
    if groq:
        try:
            body = json.dumps({"model": os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile", "temperature": 0.2,
                               "messages": [{"role": "user", "content": domanda}]}).encode()
            r = json.loads(http("https://api.groq.com/openai/v1/chat/completions", body,
                                {"Authorization": f"Bearer {groq}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}))
            return r["choices"][0]["message"]["content"]
        except Exception as e:
            print("Groq non disponibile:", str(e)[:150])
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        try:
            body = json.dumps({"contents": [{"role": "user", "parts": [{"text": domanda}]}]}).encode()
            r = json.loads(http("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent",
                                body, {"Content-Type": "application/json", "x-goog-api-key": key}, timeout=90))
            return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"] if not p.get("thought"))
        except Exception as e:
            print("Gemini non disponibile:", str(e)[:150])
    return testo

# ---------- foto indicata con un link Unsplash preciso ----------
LINK = re.search(r"https?://(?:www\.)?unsplash\.com/(?:[a-z]{2}/)?(?:photos|foto)/[^\s\"']+|https?://images\.unsplash\.com/photo-[^\s\"']+", RICHIESTA)

def foto_da_link(link):
    """Verifica il link Unsplash: la foto deve esistere ed essere gratuita (non Unsplash+). Restituisce (url, credito)."""
    if "images.unsplash.com" in link:
        base_img = link.split("?")[0]
        if not re.fullmatch(r"https://images\.unsplash\.com/photo-[0-9a-f]+-[0-9a-f]+", base_img):
            sys.exit("ERRORE: link immagine Unsplash non valido: " + link)
        http(base_img + "?w=50", headers=foto.UA, timeout=30)  # deve rispondere (404 = foto inesistente)
        return base_img + "?w=1600&q=80&fm=jpg&fit=max", "Foto: Unsplash"
    pid = re.sub(r"[/?#].*$", "", link.rstrip("/").split("/")[-1]).split("-")[-1]
    if not re.fullmatch(r"[A-Za-z0-9_]{11}", pid):
        sys.exit("ERRORE: link Unsplash non valido (manca l'ID della foto): " + link)
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        sys.exit("ERRORE: per usare un link Unsplash serve il segreto UNSPLASH_ACCESS_KEY")
    h = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1", **foto.UA}
    try:
        f = json.loads(http(f"https://api.unsplash.com/photos/{pid}", headers=h))
    except Exception as e:
        sys.exit(f"ERRORE: la foto Unsplash {pid} non esiste o non è raggiungibile ({str(e)[:80]})")
    if f.get("premium") or f.get("plus"):
        sys.exit("ERRORE: la foto è Unsplash+ (a pagamento), scegline una gratuita: " + link)
    try:
        http(f["links"]["download_location"], headers=h, timeout=20)  # conteggio download richiesto da Unsplash
    except Exception:
        pass
    return f["urls"]["raw"] + "&w=1600&q=80&fm=jpg&fit=max", f"Foto: {f.get('user', {}).get('name', 'Unsplash')} / Unsplash"

if LINK:
    print("Link foto indicato:", LINK.group(0))
    parole = ""
else:
    parole = " ".join(re.findall(r"[A-Za-z]+", parole_inglesi(base)))[:80] or base
    print("Parole chiave foto:", parole)

# ---------- cerca una foto DIVERSA da quella attuale ----------
attuale = meta.get("immagine", "")
id_attuale = (re.search(r"photo-[0-9a-f-]+", attuale) or [""])[0]

def unsplash_diversa(q):
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return None
    h = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1", **foto.UA}
    r = json.loads(http("https://api.unsplash.com/search/photos?per_page=15&orientation=landscape&content_filter=high&query="
                        + urllib.parse.quote(q), headers=h))
    for f in r.get("results", []):
        if id_attuale and id_attuale in f["urls"]["raw"]:
            continue
        try:
            http(f["links"]["download_location"], headers=h, timeout=20)  # conteggio download richiesto da Unsplash
        except Exception:
            pass
        return f["urls"]["raw"] + "&w=1600&q=80&fm=jpg&fit=max", f"Foto: {f.get('user', {}).get('name', 'Unsplash')} / Unsplash"
    return None

slug = nome[:-3]
ris = foto_da_link(LINK.group(0)) if LINK else None
for q in (() if LINK else (parole, " ".join(parole.split()[:2]))):
    try:
        ris = unsplash_diversa(q)
    except Exception as e:
        print("Errore Unsplash:", str(e)[:150])
    if ris:
        break
if not ris and not LINK:
    url, credito = foto.cerca_foto(parole, slug, base)
    ris = (url, credito) if url and url != attuale else None
if not ris:
    sys.exit("ERRORE: nessuna nuova foto trovata per: " + parole)
url, credito = ris
print("Nuova foto:", url)

# ---------- aggiorna l'articolo ----------
if re.search(r"^immagine:.*$", raw, re.M):
    raw = re.sub(r"^immagine:.*$", "immagine: " + url, raw, count=1, flags=re.M)
else:
    raw = raw.replace("---\n", "---\nimmagine: " + url + "\n", 1)
raw = re.sub(r"^foto_cercata:.*\n", "", raw, flags=re.M)
corpo = raw.rstrip("\n")
righe = corpo.split("\n")
if righe and righe[-1].startswith("Foto:"):
    righe[-1] = credito
    corpo = "\n".join(righe)
elif credito:
    corpo += "\n\n" + credito
open(os.path.join(CARTELLA, nome), "w", encoding="utf-8").write(corpo + "\n")
print("Foto aggiornata in", nome)
