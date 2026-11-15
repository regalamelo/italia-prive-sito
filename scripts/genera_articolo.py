#!/usr/bin/env python3
"""Scrive un articolo in ottica GEO con Gemini (piano gratuito) e cerca una foto su Pexels.

Uso: ARGOMENTO="..." [CATEGORIA="news"] python3 scripts/genera_articolo.py
Segreti: GEMINI_API_KEY (obbligatorio), PEXELS_API_KEY (facoltativo, per la foto)
Variabili del sito: SITO_NOME, SITO_TEMA, CATEGORIE, GEMINI_MODEL (facoltativa)
Risultato: articoli/<slug>.md (+ extra/img/articoli/<slug>.jpg)
"""
import datetime, json, os, re, sys, unicodedata, urllib.parse, urllib.request

ARG = (os.environ.get("ARGOMENTO") or "").strip()
if not ARG:
    sys.exit("ERRORE: manca l'argomento")
KEY = os.environ.get("GEMINI_API_KEY") or sys.exit("ERRORE: manca il segreto GEMINI_API_KEY")
CATEGORIE = [c.strip() for c in os.environ.get("CATEGORIE", "news").split(",") if c.strip()]
CAT_RICHIESTA = (os.environ.get("CATEGORIA") or "").strip().lower()
SITO = os.environ.get("SITO_NOME", "il sito")
TEMA = os.environ.get("SITO_TEMA", "")
MODELLI = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-flash-latest", "gemini-2.5-flash"] if m]
OGGI = datetime.date.today().isoformat()

def http(url, data=None, headers=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def slugify(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:70] or "articolo"

PROMPT = f"""Sei il caporedattore di {SITO}. {('Il sito: ' + TEMA) if TEMA else ''}
Scrivi in italiano un articolo originale sull'argomento: "{ARG}".

Obiettivo GEO (essere citati dalle IA come ChatGPT, Gemini, Perplexity) e SEO:
- apri con un paragrafo di 2-3 frasi che risponde subito alla domanda principale;
- usa sottotitoli chiari (righe che iniziano con "## "), paragrafi brevi, almeno un elenco puntato (righe che iniziano con "- ");
- inserisci dati concreti e verificabili (luoghi, date, nomi, numeri) solo se sei sicuro che siano veri: niente invenzioni, niente citazioni inventate;
- chiudi con la sezione "## Domande frequenti" con 3-5 domande (righe "### Domanda?") ciascuna seguita da una risposta di 2-3 frasi;
- lunghezza 700-1100 parole, tono {('coerente con il sito' if TEMA else 'professionale e accessibile')}, niente frasi promozionali vuote;
- puoi usare **grassetto** per i concetti chiave.
Categoria: scegli una tra {", ".join(CATEGORIE)}{(" (preferibilmente " + CAT_RICHIESTA + ")") if CAT_RICHIESTA else ""}.
Per la foto indica 2-4 parole chiave IN INGLESE adatte a cercare una foto reale su un archivio di immagini."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "titolo": {"type": "STRING"},
        "descrizione": {"type": "STRING", "description": "max 155 caratteri"},
        "categoria": {"type": "STRING", "enum": CATEGORIE},
        "parole_chiave_foto": {"type": "STRING"},
        "testo": {"type": "STRING", "description": "corpo dell'articolo in markdown semplice, senza il titolo"},
    },
    "required": ["titolo", "descrizione", "categoria", "parole_chiave_foto", "testo"],
}

def gemini():
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0.8},
    }).encode()
    ultimo = None
    for modello in MODELLI:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent"
        try:
            r = json.loads(http(url, body, {"Content-Type": "application/json", "x-goog-api-key": KEY}))
            testo = r["candidates"][0]["content"]["parts"][0]["text"]
            print("Modello usato:", modello)
            return json.loads(testo)
        except Exception as e:
            ultimo = e
            print("Modello", modello, "non disponibile:", getattr(e, "code", ""), str(e)[:200])
    sys.exit(f"ERRORE Gemini: {ultimo}")

def foto(parole, slug):
    pk = os.environ.get("PEXELS_API_KEY")
    if not pk:
        return ""
    try:
        q = urllib.parse.quote(parole)
        r = json.loads(http(f"https://api.pexels.com/v1/search?query={q}&per_page=5&orientation=landscape",
                            headers={"Authorization": pk, "User-Agent": "Mozilla/5.0"}))
        if not r.get("photos"):
            return ""
        src = r["photos"][0]["src"]["large2x"]
        img = http(src, headers={"User-Agent": "Mozilla/5.0"})
        os.makedirs("extra/img/articoli", exist_ok=True)
        open(f"extra/img/articoli/{slug}.jpg", "wb").write(img)
        print("Foto:", r["photos"][0].get("url"))
        return f"/img/articoli/{slug}.jpg"
    except Exception as e:
        print("Foto non trovata:", e)
        return ""

a = gemini()
titolo = " ".join(a["titolo"].split())
slug = slugify(os.environ.get("SLUG") or titolo)
categoria = a.get("categoria", "").lower()
if CAT_RICHIESTA in CATEGORIE:
    categoria = CAT_RICHIESTA
immagine = foto(a.get("parole_chiave_foto", ARG), slug)
testo = re.sub(r"^#\s+.*\n", "", a["testo"].strip()).strip()  # niente titolo H1 duplicato

meta = {"titolo": titolo, "descrizione": " ".join(a["descrizione"].split())[:200],
        "categoria": categoria, "immagine": immagine, "data": OGGI, "argomento": " ".join(ARG.split())}
righe = ["---"] + [f"{k}: {v}" for k, v in meta.items() if v] + ["---", testo, ""]
os.makedirs("articoli", exist_ok=True)
open(f"articoli/{slug}.md", "w", encoding="utf-8").write("\n".join(righe))
print("Articolo creato: articoli/%s.md" % slug)
if os.environ.get("GITHUB_OUTPUT"):
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"slug={slug}\n")
