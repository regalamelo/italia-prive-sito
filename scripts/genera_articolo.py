#!/usr/bin/env python3
"""Scrive un articolo in ottica GEO con Gemini (piano gratuito) e cerca una foto (Pexels se c'è la chiave, altrimenti Openverse: licenze libere, senza chiave).

Uso: ARGOMENTO="..." [CATEGORIA="news"] python3 scripts/genera_articolo.py
Segreti: GEMINI_API_KEY (obbligatorio), PEXELS_API_KEY (facoltativo, per la foto)
Variabili del sito: SITO_NOME, SITO_TEMA, CATEGORIE, GEMINI_MODEL (facoltativa)
Risultato: articoli/<slug>.md (+ extra/img/articoli/<slug>.jpg)
"""
import datetime, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

sys.stdout.reconfigure(line_buffering=True)  # log visibili subito su GitHub

ARG = (os.environ.get("ARGOMENTO") or "").strip()
if not ARG:
    sys.exit("ERRORE: manca l'argomento")
KEY = os.environ.get("GEMINI_API_KEY") or sys.exit("ERRORE: manca il segreto GEMINI_API_KEY")
CATEGORIE = [c.strip() for c in os.environ.get("CATEGORIE", "news").split(",") if c.strip()]
CAT_RICHIESTA = (os.environ.get("CATEGORIA") or "").strip().lower()
SITO = os.environ.get("SITO_NOME", "il sito")
TEMA = os.environ.get("SITO_TEMA", "")
MODELLI = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-flash-latest"] if m]
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

def modelli_disponibili():
    """Elenco dei modelli Flash attivi per questa chiave (i nomi cambiano nel tempo)."""
    try:
        r = json.loads(http("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                            headers={"x-goog-api-key": KEY}, timeout=30))
        nomi = [m["name"].split("/", 1)[1] for m in r.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [n for n in nomi if "flash" in n and not re.search(r"image|tts|audio|live|lite|exp|preview|thinking", n)]
        return sorted(flash, reverse=True)
    except Exception as e:
        print("Elenco modelli non disponibile:", e)
        return []

def chiama(modello, gen_cfg):
    """Risposta in streaming: se Gemini resta muto per 90 secondi si passa oltre (niente attese infinite)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:streamGenerateContent?alt=sse"
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": PROMPT}]}], "generationConfig": gen_cfg}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
    parti = []
    with urllib.request.urlopen(req, timeout=90) as r:
        for riga in r:
            riga = riga.decode("utf-8", "ignore").strip()
            if not riga.startswith("data:"):
                continue
            d = json.loads(riga[5:])
            for c in d.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    if not p.get("thought"):
                        parti.append(p.get("text", ""))
    return json.loads("".join(parti))

def gemini():
    base = {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0.8}
    configurazioni = [dict(base, thinkingConfig={"thinkingLevel": "low"}),
                      dict(base, thinkingConfig={"thinkingBudget": 0}),
                      base]
    candidati = []
    for m in MODELLI + modelli_disponibili():
        if m not in candidati:
            candidati.append(m)
    print("Modelli da provare:", candidati[:4])
    inizio, ultimo = time.time(), None
    for modello in candidati[:4]:
        for cfg in configurazioni:
            if time.time() - inizio > 480:
                sys.exit(f"ERRORE Gemini: troppo tempo ({ultimo})")
            try:
                t0 = time.time()
                a = chiama(modello, cfg)
                print(f"Modello usato: {modello} ({int(time.time() - t0)} s)")
                return a
            except urllib.error.HTTPError as e:
                ultimo = e
                dettaglio = e.read().decode("utf-8", "ignore")[:300]
                print("Modello", modello, "errore", e.code, dettaglio)
                if e.code == 400:
                    continue      # impostazione non supportata da questo modello: prova la successiva
                break             # 404/429/500: passa al modello successivo
            except Exception as e:
                ultimo = e
                print("Modello", modello, "non risponde:", str(e)[:200])
                break
    sys.exit(f"ERRORE Gemini: {ultimo}")

def salva(img, slug):
    os.makedirs("extra/img/articoli", exist_ok=True)
    open(f"extra/img/articoli/{slug}.jpg", "wb").write(img)
    return f"/img/articoli/{slug}.jpg"

def foto_pexels(parole, slug):
    pk = os.environ.get("PEXELS_API_KEY")
    if not pk:
        return "", ""
    q = urllib.parse.quote(parole)
    r = json.loads(http(f"https://api.pexels.com/v1/search?query={q}&per_page=5&orientation=landscape",
                        headers={"Authorization": pk, "User-Agent": "Mozilla/5.0"}))
    if not r.get("photos"):
        return "", ""
    f = r["photos"][0]
    return salva(http(f["src"]["large2x"], headers={"User-Agent": "Mozilla/5.0"}), slug), ""

def foto_openverse(parole, slug):
    """Foto con licenza libera per uso commerciale (nessuna chiave richiesta). Restituisce anche il credito."""
    q = urllib.parse.quote(parole)
    url = f"https://api.openverse.org/v1/images/?q={q}&license_type=commercial&aspect_ratio=wide&size=large&page_size=10"
    r = json.loads(http(url, headers={"User-Agent": "Mozilla/5.0 (sito-articoli)"}))
    for f in r.get("results", []):
        try:
            img = http(f["url"], headers={"User-Agent": "Mozilla/5.0 (sito-articoli)"}, timeout=60)
            if len(img) < 20000:
                continue
            lic = (f.get("license") or "").upper()
            ver = f.get("license_version") or ""
            credito = f"Foto: {f.get('title') or 'immagine'} di {f.get('creator') or 'autore sconosciuto'}, licenza {lic if lic in ('CC0', 'PDM') else 'CC ' + lic} {ver}".strip()
            print("Foto:", f.get("foreign_landing_url"))
            return salva(img, slug), credito
        except Exception:
            continue
    return "", ""

def foto(parole, slug):
    for fn in (foto_pexels, foto_openverse):
        try:
            percorso, credito = fn(parole, slug)
            if percorso:
                return percorso, credito
        except Exception as e:
            print("Foto non trovata con", fn.__name__, ":", e)
    return "", ""

a = gemini()
titolo = " ".join(a["titolo"].split())
slug = slugify(os.environ.get("SLUG") or titolo)
categoria = a.get("categoria", "").lower()
if CAT_RICHIESTA in CATEGORIE:
    categoria = CAT_RICHIESTA
immagine, credito = foto(a.get("parole_chiave_foto", ARG), slug)
testo = re.sub(r"^#\s+.*\n", "", a["testo"].strip()).strip()  # niente titolo H1 duplicato
if credito:
    testo += "\n\n" + credito

meta = {"titolo": titolo, "descrizione": " ".join(a["descrizione"].split())[:200],
        "categoria": categoria, "immagine": immagine, "data": OGGI, "argomento": " ".join(ARG.split())}
righe = ["---"] + [f"{k}: {v}" for k, v in meta.items() if v] + ["---", testo, ""]
os.makedirs("articoli", exist_ok=True)
open(f"articoli/{slug}.md", "w", encoding="utf-8").write("\n".join(righe))
print("Articolo creato: articoli/%s.md" % slug)
if os.environ.get("GITHUB_OUTPUT"):
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"slug={slug}\n")
