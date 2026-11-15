#!/usr/bin/env python3
"""Scrive un articolo in ottica GEO con Gemini (piano gratuito) e cerca una foto (Pexels se c'è la chiave, altrimenti Openverse: licenze libere, senza chiave).

Uso: ARGOMENTO="..." [CATEGORIA="news"] python3 scripts/genera_articolo.py
Segreti: GEMINI_API_KEY e/o GROQ_API_KEY (piano B, veloce), PEXELS_API_KEY (facoltativo, per la foto)
Variabili del sito: SITO_NOME, SITO_TEMA, CATEGORIE, GEMINI_MODEL (facoltativa)
Risultato: articoli/<slug>.md (+ extra/img/articoli/<slug>.jpg)
"""
import datetime, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

sys.stdout.reconfigure(line_buffering=True)  # log visibili subito su GitHub
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto import cerca_foto

ARG = (os.environ.get("ARGOMENTO") or "").strip()
if not ARG:
    sys.exit("ERRORE: manca l'argomento")
if "{%" in ARG or "%}" in ARG:
    sys.exit("ERRORE: argomento non valido (variabile Albato non sostituita): " + ARG)
KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ = os.environ.get("GROQ_API_KEY", "")
if not KEY and not GROQ:
    sys.exit("ERRORE: manca il segreto GEMINI_API_KEY (o GROQ_API_KEY)")
LIMITE_GEMINI = 240 if GROQ else 720  # con Groq di riserva non si aspetta troppo Gemini
CATEGORIE = [c.strip() for c in os.environ.get("CATEGORIE", "news").split(",") if c.strip()]
CAT_RICHIESTA = (os.environ.get("CATEGORIA") or "").strip().lower()
if CAT_RICHIESTA not in CATEGORIE:  # categoria vuota o non valida: la sceglie l'IA
    CAT_RICHIESTA = ""
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
        flash = [n for n in nomi if "flash" in n and not re.search(r"image|tts|audio|live|exp|preview|thinking|omni", n)]
        # prima i Flash normali (dal piu' recente), poi i "lite" (piu' veloci e spesso piu' disponibili)
        return sorted(flash, key=lambda n: ("lite" in n, [-int(x) for x in re.findall(r"\d+", n)]))
    except Exception as e:
        print("Elenco modelli non disponibile:", e)
        return []

def chiama(modello, gen_cfg):
    """Risposta in streaming: se Gemini resta muto per 150 secondi si passa oltre (niente attese infinite)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:streamGenerateContent?alt=sse"
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": PROMPT}]}], "generationConfig": gen_cfg}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
    parti = []
    with urllib.request.urlopen(req, timeout=150) as r:
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
    print("Modelli da provare:", candidati[:6])
    inizio, ultimo = time.time(), None
    for modello in candidati[:6]:
        for cfg in configurazioni:
            if time.time() - inizio > LIMITE_GEMINI:
                raise RuntimeError(f"Gemini: troppo tempo ({ultimo})")
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
                if e.code in (500, 503):
                    time.sleep(20)  # server sovraccarico: riprova lo stesso modello
                    continue
                break             # 404/429: passa al modello successivo
            except Exception as e:
                ultimo = e
                print("Modello", modello, "non risponde:", str(e)[:200])
                break
    raise RuntimeError(f"Gemini: {ultimo}")

def groq():
    """Piano B: Groq (gratuito, risposte in pochi secondi), API compatibile OpenAI."""
    h = {"Authorization": f"Bearer {GROQ}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    preferiti = [os.environ.get("GROQ_MODEL"), "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct"]
    try:
        attivi = [m["id"] for m in json.loads(http("https://api.groq.com/openai/v1/models", headers=h, timeout=30)).get("data", [])]
    except Exception as e:
        print("Elenco modelli Groq non disponibile:", e)
        attivi = []
    candidati = [m for m in preferiti if m and (not attivi or m in attivi)]
    candidati += [m for m in attivi if m not in candidati and not re.search(r"whisper|guard|tts|vision|compound", m)][:3]
    istruzioni = (PROMPT + "\n\nRispondi SOLO con un oggetto JSON con le chiavi: titolo, descrizione, categoria "
                  f"(una tra {', '.join(CATEGORIE)}), parole_chiave_foto, testo (markdown, senza il titolo).")
    ultimo = None
    for modello in candidati[:4]:
        body = json.dumps({"model": modello, "temperature": 0.8, "response_format": {"type": "json_object"},
                           "messages": [{"role": "user", "content": istruzioni}]}).encode()
        try:
            t0 = time.time()
            r = json.loads(http("https://api.groq.com/openai/v1/chat/completions", body, h, timeout=180))
            a = json.loads(r["choices"][0]["message"]["content"])
            if a.get("titolo") and a.get("testo"):
                print(f"Modello usato: Groq {modello} ({int(time.time() - t0)} s)")
                return a
        except Exception as e:
            ultimo = e
            dettaglio = e.read().decode("utf-8", "ignore")[:300] if hasattr(e, "read") else ""
            print("Groq", modello, "errore:", str(e)[:200], dettaglio)
    raise RuntimeError(f"Groq: {ultimo}")

def scrivi():
    errori = []
    for nome, fn, attivo in (("Gemini", gemini, KEY), ("Groq", groq, GROQ)):
        if not attivo:
            continue
        try:
            return fn()
        except Exception as e:
            print(f"{nome} non disponibile, provo il successivo:", e)
            errori.append(str(e))
    sys.exit("ERRORE: nessuna IA disponibile - " + " | ".join(errori))

a = scrivi()
titolo = " ".join(a["titolo"].split())
slug = slugify(os.environ.get("SLUG") or titolo)
categoria = a.get("categoria", "").lower()
if CAT_RICHIESTA in CATEGORIE:
    categoria = CAT_RICHIESTA
immagine, credito = cerca_foto(a.get("parole_chiave_foto", ""), slug, ARG)
testo = re.sub(r"^#\s+.*\n", "", a["testo"].strip()).strip()  # niente titolo H1 duplicato
if credito:
    testo += "\n\n" + credito

meta = {"titolo": titolo, "descrizione": " ".join(str(a.get("descrizione", "")).split())[:200],
        "categoria": categoria, "immagine": immagine, "data": OGGI, "argomento": " ".join(ARG.split())}
righe = ["---"] + [f"{k}: {v}" for k, v in meta.items() if v] + ["---", testo, ""]
os.makedirs("articoli", exist_ok=True)
open(f"articoli/{slug}.md", "w", encoding="utf-8").write("\n".join(righe))
print("Articolo creato: articoli/%s.md" % slug)
if os.environ.get("GITHUB_OUTPUT"):
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"slug={slug}\n")
