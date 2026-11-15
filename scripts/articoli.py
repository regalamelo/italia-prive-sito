#!/usr/bin/env python3
"""Crea le pagine degli articoli in articoli/*.md usando come modello
grafico un articolo Brizy esistente (stesso stile, menu e piè di pagina).

Formato di un articolo (articoli/<indirizzo>.md):
---
titolo: Titolo dell'articolo
descrizione: Frase per Google e per le anteprime social
immagine: https://... (facoltativa, consigliata)
categoria: news | tendenze | storie | eccellenze (facoltativa)
data: 2026-11-14 (facoltativa)
---
Primo paragrafo.

Secondo paragrafo. Si può usare **grassetto**.
"""
import datetime, html, json, os, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto import cerca_foto

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
    blocchi_testo = []
    for b in re.split(r"\n\s*\n", corpo):
        righe = [r.strip() for r in b.strip().split("\n") if r.strip()]
        # titoli e voci di elenco su righe separate diventano blocchi separati
        corrente = []
        for r in righe:
            if r.startswith(("#", "- ", "* ")):
                if corrente:
                    blocchi_testo.append(" ".join(corrente)); corrente = []
                blocchi_testo.append(r)
            else:
                corrente.append(r)
        if corrente:
            blocchi_testo.append(" ".join(corrente))
    return meta, blocchi_testo

SITO_NOME = os.environ.get("SITO_NOME", "")

def corpo_html(blocchi_testo, tag_p):
    """Markdown semplice -> HTML con lo stile dei paragrafi Brizy (## sottotitolo, ### domanda, - elenco)."""
    cls = re.search(r'class="([^"]*)"', tag_p)
    cls = cls.group(1) if cls else ""
    out, elenco = [], []
    def chiudi():
        if elenco:
            out.append('<ul style="padding-left:1.3em;margin:0 0 1em;list-style:disc">' + "".join(
                f'<li class="{cls}" style="margin-bottom:.3em"><span class="brz-cp-color7">{testo(x)}</span></li>' for x in elenco) + "</ul>")
            elenco.clear()
    for b in blocchi_testo:
        if b.startswith(("- ", "* ")):
            elenco.append(b[2:].strip()); continue
        chiudi()
        if b.startswith("### "):
            out.append(f'<h3 class="{cls}" style="font-size:1.12em;font-weight:600;margin:1.2em 0 .3em"><span class="brz-cp-color7">{testo(b[4:])}</span></h3>')
        elif b.startswith("## ") or b.startswith("# "):
            out.append(f'<h2 class="{cls}" style="font-size:1.35em;font-weight:600;margin:1.6em 0 .4em"><span class="brz-cp-color7">{testo(b.lstrip("#").strip())}</span></h2>')
        else:
            out.append(f'{tag_p}<span class="brz-cp-color7">{testo(b)}</span></p>')
    chiudi()
    return "".join(out)

def faq_da(blocchi_testo):
    faq, dentro, dom, risp = [], False, None, []
    for b in blocchi_testo + ["## fine"]:
        if b.startswith("## ") or b.startswith("# "):
            if dom and risp: faq.append((dom, " ".join(risp)))
            dom, risp = None, []
            dentro = bool(re.search(r"domande|faq", b, re.I))
        elif dentro and b.startswith("### "):
            if dom and risp: faq.append((dom, " ".join(risp)))
            dom, risp = b[4:].strip(), []
        elif dentro and dom:
            risp.append(re.sub(r"\*\*(.+?)\*\*", r"\1", b.lstrip("-* ")))
    return faq

def schema_ld(titolo, descr, slug, data, immagine, faq):
    base = DOMINIO.rstrip("/")
    img = immagine if immagine.startswith("http") else (base + immagine if immagine else "")
    art = {"@context": "https://schema.org", "@type": "Article", "headline": titolo, "description": descr,
           "datePublished": data, "dateModified": data, "inLanguage": "it-IT",
           "mainEntityOfPage": f"{base}/{slug}",
           "author": {"@type": "Organization", "name": SITO_NOME or base},
           "publisher": {"@type": "Organization", "name": SITO_NOME or base, "url": base}}
    if img: art["image"] = img
    blocchi_ld = [art]
    if faq:
        blocchi_ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": r}} for q, r in faq]})
    return "".join('<script type="application/ld+json">' + json.dumps(b, ensure_ascii=False).replace("</", "<\\/") + "</script>" for b in blocchi_ld)

def testo(t):
    t = html.escape(t, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r'<strong class="brz-cp-color7 brz-bold-true">\1</strong>', t)

if not os.path.isdir(ARTICOLI):
    sys.exit(0)
modello = open(os.path.join(SITE, MODELLO), encoding="utf-8").read()
slug_modello = MODELLO[:-5]
nuovi = []
schede = []

for nome in sorted(os.listdir(ARTICOLI)):
    if not nome.endswith(".md") or nome.startswith("_"):
        continue
    slug = nome[:-3]
    meta, paragrafi = leggi(os.path.join(ARTICOLI, nome))
    titolo = meta.get("titolo", slug.replace("-", " ").capitalize())

    # articolo senza foto: la cerca una volta sola e la aggiunge al file
    if not meta.get("immagine") and meta.get("foto_cercata") != "si":
        percorso, credito = cerca_foto(meta.get("foto", ""), slug, meta.get("argomento") or titolo)
        f_md = os.path.join(ARTICOLI, nome)
        raw = open(f_md, encoding="utf-8").read()
        extra_meta = (f"immagine: {percorso}\n" if percorso else "") + "foto_cercata: si\n"
        raw = re.sub(r"^---\n", "---\n" + extra_meta, raw, count=1) if raw.startswith("---\n") else "---\n" + extra_meta + "---\n" + raw
        if credito:
            raw = raw.rstrip("\n") + "\n\n" + credito + "\n"
            paragrafi.append(credito)
        open(f_md, "w", encoding="utf-8").write(raw)
        if percorso:
            meta["immagine"] = percorso
            os.makedirs(os.path.join(SITE, "img", "articoli"), exist_ok=True)
            shutil.copy2("extra" + percorso, os.path.join(SITE, percorso.lstrip("/")))
    descr = meta.get("descrizione", re.sub(r"[#*]", "", paragrafi[0])[:155].strip() if paragrafi else titolo)
    h = modello

    # <head>: titolo, descrizione, indirizzi
    h = re.sub(r"<title>.*?</title>", f"<title>{html.escape(titolo)}{(' | ' + html.escape(SITO_NOME)) if SITO_NOME else ''}</title>", h, count=1, flags=re.S)
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
    h = h[:p_aperto] + corpo_html(paragrafi, tag_p) + h[fine:]
    data_art = meta.get("data") or datetime.date.today().isoformat()
    h = h.replace("</head>", schema_ld(titolo, descr, slug, data_art, meta.get("immagine", ""), faq_da(paragrafi)) + "</head>", 1)

    open(os.path.join(SITE, slug + ".html"), "w", encoding="utf-8").write(h)
    nuovi.append((slug, meta.get("data") or datetime.date.today().isoformat()))
    schede.append({"slug": slug, "titolo": titolo, "descr": descr, "immagine": meta.get("immagine", ""),
                   "categoria": meta.get("categoria", "").lower().strip(), "data": nuovi[-1][1]})
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

# ---------- elenchi articoli (home e pagine categoria) ----------
CATEGORIE = [c.strip() for c in os.environ.get("CATEGORIE", "news,tendenze,storie,eccellenze").split(",") if c.strip()]
WRAP = '<div class="brz-posts__wrapper">'
ITEM = '<div class="brz-posts__item">'

def fine_div(h, i):
    """posizione subito dopo il </div> che chiude il <div> che inizia in i"""
    d = 0
    for m in re.finditer(r"<(/?)div\b[^>]*>", h[i:]):
        d += -1 if m.group(1) else 1
        if d == 0:
            return i + m.end()
    return len(h)

def blocchi(h):
    out = []
    i = h.find(WRAP)
    while i >= 0:
        e = fine_div(h, i)
        items, j = [], i + len(WRAP)
        while h.startswith(ITEM, j):
            k = fine_div(h, j)
            items.append(h[j:k])
            j = k
        out.append((i, e, items))
        i = h.find(WRAP, e)
    return out

def slug_di(item):
    m = re.search(r'href="([^"#/][^"]*)"', item)
    return m.group(1) if m else ""

def scheda(modello, a):
    vecchio = slug_di(modello)
    c = modello.replace(f'href="{vecchio}"', f'href="{a["slug"]}"')
    c = re.sub(r'(class="brz-wp-title-content"[^>]*>).*?(</)', lambda m: m.group(1) + html.escape(a["titolo"]) + m.group(2), c, flags=re.S)
    c = re.sub(r'(class="brz-wp-post-excerpt-content"[^>]*>).*?(</)', lambda m: m.group(1) + html.escape(a["descr"]) + m.group(2), c, flags=re.S)
    if a["immagine"]:
        url = html.escape(a["immagine"])
        def pic(m):
            p = re.sub(r"<source[^>]*>", "", m.group(0))
            p = re.sub(r'\ssrcset="[^"]*"', "", p)
            p = re.sub(r'\ssrc="[^"]*"', f' src="{url}"', p)
            p = re.sub(r'\salt="[^"]*"', f' alt="{html.escape(a["titolo"])}"', p)
            return p.replace("<img ", '<img style="object-fit:cover;width:100%;height:100%" ', 1)
        c = re.sub(r"<picture.*?</picture>", pic, c, flags=re.S)
    return c

if schede:
    schede.sort(key=lambda a: a["data"], reverse=True)
    ordine = {}
    for cat in CATEGORIE:
        f = os.path.join(SITE, cat + ".html")
        if os.path.exists(f):
            hc = open(f, encoding="utf-8").read()
            ordine[cat] = [slug_di(it) for _, _, its in blocchi(hc) for it in its]
    pagine = ["index.html"] + [c + ".html" for c in ordine]
    for pag in pagine:
        f = os.path.join(SITE, pag)
        h = open(f, encoding="utf-8").read()
        cat_pagina = pag[:-5] if pag != "index.html" else None
        for i, e, items in reversed(blocchi(h)):
            if not items:
                continue
            slugs = [slug_di(it) for it in items]
            if cat_pagina:
                cat = cat_pagina
            else:
                cat = next((c for c, lst in ordine.items() if lst[:len(slugs)] == slugs), "tutte")
            da_aggiungere = [a for a in schede if (cat == "tutte" or a["categoria"] == cat) and a["slug"] not in slugs]
            if not da_aggiungere:
                continue
            nuovi_items = [scheda(items[0], a) for a in da_aggiungere] + items
            if not cat_pagina:
                nuovi_items = nuovi_items[:len(items)]   # in home resta lo stesso numero di articoli
            h = h[:i] + WRAP + "".join(nuovi_items) + h[i + len(WRAP) + sum(map(len, items)):]
            print(f"{pag}: elenco '{cat}' aggiornato")
        open(f, "w", encoding="utf-8").write(h)
