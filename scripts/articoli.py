#!/usr/bin/env python3
"""Crea le pagine degli articoli in articoli/*.md usando come modello
grafico un articolo Brizy esistente (stesso stile, menu e piè di pagina).

Formato di un articolo (articoli/<indirizzo>.md):
---
titolo: Titolo dell'articolo
descrizione: Frase per Google e per le anteprime social
immagine: https://... (facoltativa)
data: 2026-11-14 (facoltativa)
---
Primo paragrafo.

Secondo paragrafo. Si può usare **grassetto**.
"""
import datetime, html, os, re, sys

SITE, ARTICOLI = sys.argv[1], sys.argv[2]
MODELLO = os.environ.get("MODELLO_ARTICOLO", "pizze.html")
DOMINIO = os.environ.get("DOMINIO", "https://www.italiaprive.it")

def leggi(path):
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    meta, corpo = {}, raw
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    if m:
        for riga in m.group(1).splitlines():
            if ":" in riga:
                k, v = riga.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        corpo = m.group(2)
    paragrafi = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", corpo) if p.strip()]
    return meta, paragrafi

def testo(t):
    t = html.escape(t, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r'<strong class="brz-cp-color7 brz-bold-true">\1</strong>', t)

if not os.path.isdir(ARTICOLI):
    sys.exit(0)
modello = open(os.path.join(SITE, MODELLO), encoding="utf-8").read()
slug_modello = MODELLO[:-5]
nuovi = []

for nome in sorted(os.listdir(ARTICOLI)):
    if not nome.endswith(".md") or nome.startswith("_"):
        continue
    slug = nome[:-3]
    meta, paragrafi = leggi(os.path.join(ARTICOLI, nome))
    titolo = meta.get("titolo", slug.replace("-", " ").capitalize())
    descr = meta.get("descrizione", paragrafi[0][:155] if paragrafi else titolo)
    h = modello

    # <head>: titolo, descrizione, indirizzi
    h = re.sub(r"<title>.*?</title>", f"<title>{html.escape(titolo)} | ITALIA PRIVÈ</title>", h, count=1, flags=re.S)
    h = re.sub(r'(<meta (?:property="og:title"|name="twitter:title") content=")[^"]*', lambda m: m.group(1) + html.escape(titolo), h)
    h = re.sub(r'(<meta (?:name="description"|property="og:description"|name="twitter:description") content=")[^"]*', lambda m: m.group(1) + html.escape(descr), h)
    h = h.replace(f"/{slug_modello}\"", f"/{slug}\"")

    # titolo visibile (primo <h3> del contenuto)
    h = re.sub(r"(<h3[^>]*><span[^>]*>).*?(</span></h3>)", lambda m: m.group(1) + html.escape(titolo) + m.group(2), h, count=1, flags=re.S)
    inizio_titolo = h.find(html.escape(titolo) + "</span></h3>")

    # immagine principale (la prima dopo il titolo)
    if meta.get("immagine"):
        p0 = h.find("<picture", inizio_titolo)
        p1 = h.find("</picture>", p0)
        img = re.search(r'<img class="([^"]*)"', h[p0:p1])
        cls = img.group(1) if img else "brz-img"
        url = html.escape(meta["immagine"])
        apertura = h[p0:h.find(">", p0) + 1]
        h = h[:p0] + f'{apertura}<img class="{cls}" src="{url}" alt="{html.escape(titolo)}" loading="lazy" draggable="false" style="width:100%;height:auto">' + h[p1:]
        h = re.sub(r'(<meta (?:property="og:image"|property="twitter:image") content=")[^"]*', lambda m: m.group(1) + url, h)

    # testo: sostituisce i paragrafi del blocco di testo dopo l'immagine
    blocco = h.find('<div data-brz-translate-text="1"><p ', inizio_titolo)
    p_aperto = h.find("<p ", blocco)
    tag_p = h[p_aperto:h.find(">", p_aperto) + 1]
    fine = h.find("</div>", p_aperto)
    nuovo = "".join(f'{tag_p}<span class="brz-cp-color7">{testo(p)}</span></p>' for p in paragrafi)
    h = h[:p_aperto] + nuovo + h[fine:]

    open(os.path.join(SITE, slug + ".html"), "w", encoding="utf-8").write(h)
    nuovi.append((slug, meta.get("data") or datetime.date.today().isoformat()))
    print("Articolo creato:", slug)

# sitemap
smp = os.path.join(SITE, "sitemap.xml")
if nuovi and os.path.exists(smp):
    s = open(smp, encoding="utf-8").read()
    m = re.search(r"<loc>(https?://[^/<]+)/", s)
    base = m.group(1) if m else DOMINIO
    righe = "".join(f"<url><loc>{base}/{slug}</loc><lastmod>{d}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>"
                    for slug, d in nuovi if f"/{slug}<" not in s)
    open(smp, "w", encoding="utf-8").write(s.replace("</urlset>", righe + "</urlset>"))
