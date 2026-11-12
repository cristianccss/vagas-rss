#!/usr/bin/env python3
"""Coleta vagas de vários sites e gera feeds RSS em docs/.

Só usa a biblioteca padrão do Python. Rode: python3 scrape.py
Cada fonte é independente: se uma falhar, as vagas anteriores dela são mantidas.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import traceback
import urllib.request
from email.utils import format_datetime
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs")
STATE = os.path.join(OUT, "state.json")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
MAX_FEED_ITEMS = 200
FORGET_AFTER_DAYS = 120


def fetch(url, data=None, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    h.update(headers or {})
    if data is not None and not isinstance(data, bytes):
        data = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


# ---------------------------------------------------------------- fontes

def src_unimed():
    page_url = ("https://platform.senior.com.br/hcmrs/hcm/curriculo/?tenant=unimedaltovalecoopbr"
                "&tenantdomain=unimedaltovale.coop.br")
    api = ("https://platform.senior.com.br/t/senior.com.br/bridge/1.0/anonymous/rest/hcm/"
           "vacancymanagement/queries/searchPublicVacancies")
    items, page = [], 0
    while page < 10:
        body = {"q": "", "hqId": "", "currentDate": dt.date.today().isoformat(),
                "order": "HIGHLIGHT", "page": page, "size": 50}
        d = json.loads(fetch(api, body, {"x-tenant": "unimedaltovalecoopbr",
                                          "X-TenantDomain": "unimedaltovale.coop.br"}))
        for v in d.get("vacancies", []):
            link = (f"{page_url}&vacancyId={v['id']}&fromRecruitment=false"
                    f"#!/vacancies/details/{v['id']}/")
            items.append({"id": "unimed-" + v["id"], "title": v["title"].strip(),
                          "link": link, "desc": v.get("location") or ""})
        if not d.get("isMoreItemsAvailable") or not d.get("vacancies"):
            break
        page += 1
    return items


def src_sctreinamentos():
    url = "https://candidato.sctreinamentos.selecao.site/editais-abertos"
    h = fetch(url)
    items = []
    for card in re.split(r'<div class="card card-body', h)[1:]:
        org = re.search(r'<h6[^>]*>(.*?)</h6>', card, re.S)
        ed = re.search(r'<small[^>]*>(.*?)</small>', card, re.S)
        lim = re.search(r'Limite para inscri.*?<div[^>]*>(.*?)</div>', card, re.S | re.I)
        a = re.search(r'href="(https?://[^"]*/inscricao/[^"]+)"', card)
        if not org:
            continue
        title = f"{text(org.group(1))} – {text(ed.group(1)) if ed else ''}".strip(" –")
        link = a.group(1) if a else url
        items.append({"id": "sctrein-" + (a.group(1).rsplit("/", 1)[-1] if a else title),
                      "title": title, "link": link,
                      "desc": "Inscrições até " + text(lim.group(1)) if lim else ""})
    return items


def src_sesisc():
    url = "https://portaldainclusao.sesisc.org.br/oportunidades"
    h = fetch(url)
    items = []
    for card in re.split(r'<div class="card_oportunidade"', h)[1:]:
        a = re.search(r'href="(https?://[^"]*/detalhes-oportunidade/(\d+))"', card)
        t = re.search(r'class="nome-oportunidade"[^>]*>(.*?)</p>', card, re.S)
        if not a or not t:
            continue
        ps = [text(p) for p in re.findall(r'<p class="text_cinza[^"]*"[^>]*>(.*?)</p>', card, re.S)]
        city = next((p for p in ps if re.search(r"/[A-Z]{2}$", p)), "")
        title = text(t.group(1)) + (f" – {city}" if city else "")
        items.append({"id": "sesisc-" + a.group(2), "title": title, "link": a.group(1),
                      "desc": " · ".join(ps)})
    return items


def src_fiesc():
    base = "https://fiesc.pandape.infojobs.com.br"
    filt = "PageSize=20&Deficiency=2&IdLocation2List=187&IdLocation3List=5210313"
    items, seen = [], set()
    for p in range(1, 16):
        if p == 1:
            h = fetch(f"{base}/?PageNumber=1&{filt}")
        else:  # botão "Mostrar 20 vagas mais"
            r = json.loads(fetch(f"{base}/ListVacancies", f"PageNumber={p}&{filt}".encode(),
                                 {"X-Requested-With": "XMLHttpRequest",
                                  "Content-Type": "application/x-www-form-urlencoded"}))
            h = r.get("view") or ""
        new = 0
        for card in re.split(r'<a target="_blank" class="card card-vacancy', h)[1:]:
            a = re.search(r'href="(/Detail/(\d+))"', card)
            t = re.search(r'<h3[^>]*title="([^"]*)"', card)
            if not a or not t or a.group(2) in seen:
                continue
            seen.add(a.group(2)); new += 1
            body = card.split("</a>", 1)[0]
            desc = text(body.split("</h3>", 1)[-1])
            items.append({"id": "fiesc-" + a.group(2), "title": html.unescape(t.group(1)).strip(),
                          "link": base + a.group(1), "desc": desc})
        if new == 0:
            break
    return items


def src_pci():
    url = "https://www.pciconcursos.com.br/concursos/sc/rio-do-sul"
    h = fetch(url)
    items = []
    for m in re.finditer(r'<div class="(?:ea|na|da)"[^>]*data-url="([^"]+)"(.*?)<div class="clear">', h, re.S):
        link, body = m.group(1), m.group(2)
        org = re.search(r'<div class="ca"><a[^>]*>(.*?)</a>', body, re.S)
        cd = re.search(r'<div class="cd">(.*?)</div>', body, re.S)
        ce = re.search(r'<div class="ce">(.*?)</div>', body, re.S)
        if not org:
            continue
        dm = re.search(r"(\d{2})/(\d{2})/(\d{4})", ce.group(1) if ce else "")
        if not dm or dt.date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1))) < \
                dt.date.today() - dt.timedelta(days=30):
            continue  # a página também lista concursos antigos/encerrados
        cd_parts = [text(x) for x in re.split(r"<br\s*/?>", cd.group(1))] if cd else []
        title = text(org.group(1)) + (f" – {cd_parts[1]}" if len(cd_parts) > 1 else "")
        desc = " · ".join(p for p in cd_parts if p)
        if ce:
            desc += f" · Inscrições até {text(ce.group(1))}"
        items.append({"id": "pci-" + link.rstrip("/").rsplit("/", 1)[-1], "title": title,
                      "link": link, "desc": desc})
    return items


def src_cieesc():
    url = "https://cieesc.gupy.io/"
    h = fetch(url)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    jobs = json.loads(m.group(1))["props"]["pageProps"].get("jobs") or []
    items = []
    for j in jobs:
        jid = str(j.get("id"))
        place = ", ".join(x for x in [j.get("workplace", {}).get("address", {}).get("city")
                                      if isinstance(j.get("workplace"), dict) else None,
                                      j.get("city"), j.get("state")] if x)
        items.append({"id": "cieesc-" + jid, "title": (j.get("title") or j.get("name") or "").strip(),
                      "link": f"https://cieesc.gupy.io/jobs/{jid}",
                      "desc": " · ".join(x for x in [place, j.get("type") or ""] if x)})
    return items


def src_sesc():
    url = "https://sescsc.enlizt.me/?show=&department=&location=Rio+do+Sul%2C+SC"
    h = fetch(url)
    items = []
    for m in re.finditer(r'<li data-location="([^"]*)">\s*<a href="([^"]+/vagas/[^"]+)" data-title="([^"]*)"', h):
        loc, link, title = m.groups()
        if "rio do sul" not in loc.lower():
            continue
        items.append({"id": "sesc-" + link.rsplit("/", 1)[-1], "title": html.unescape(title).strip(),
                      "link": link, "desc": html.unescape(loc)})
    return items


SOURCES = [
    ("unimed", "Unimed Alto Vale", "https://platform.senior.com.br/hcmrs/hcm/curriculo/?tenant=unimedaltovalecoopbr&tenantdomain=unimedaltovale.coop.br#!/vacancies/list", src_unimed),
    ("sctreinamentos", "SC Treinamentos – editais abertos", "https://candidato.sctreinamentos.selecao.site/editais-abertos", src_sctreinamentos),
    ("sesisc", "Portal da Inclusão SESI SC", "https://portaldainclusao.sesisc.org.br/oportunidades", src_sesisc),
    ("fiesc", "FIESC – Rio do Sul (PcD)", "https://fiesc.pandape.infojobs.com.br/?PageNumber=1&PageSize=20&Deficiency=2&IdLocation2List=187&IdLocation3List=5210313", src_fiesc),
    ("pci", "PCI Concursos – Rio do Sul", "https://www.pciconcursos.com.br/concursos/sc/rio-do-sul", src_pci),
    ("cieesc", "CIEE SC (Gupy)", "https://cieesc.gupy.io/", src_cieesc),
    ("sesc", "Sesc SC – Rio do Sul", "https://sescsc.enlizt.me/?show=&department=&location=Rio+do+Sul%2C+SC", src_sesc),
]


# ---------------------------------------------------------------- saída

def rss(title, link, self_url, items):
    now = format_datetime(dt.datetime.now(dt.timezone.utc))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
           f"<title>{escape(title)}</title><link>{escape(link)}</link>",
           f"<description>{escape(title)} – atualizado automaticamente</description>",
           f"<language>pt-br</language><lastBuildDate>{now}</lastBuildDate><ttl>120</ttl>"]
    if self_url:
        out.append(f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>')
    for it in items[:MAX_FEED_ITEMS]:
        pub = format_datetime(dt.datetime.fromisoformat(it["first_seen"]))
        out.append("<item>"
                   f"<title>{escape(it['title'])}</title>"
                   f"<link>{escape(it['link'])}</link>"
                   f'<guid isPermaLink="false">{escape(it["id"])}</guid>'
                   f"<pubDate>{pub}</pubDate>"
                   f"<category>{escape(it['source_name'])}</category>"
                   f"<description>{escape(it.get('desc') or '')}</description>"
                   "</item>")
    out.append("</channel></rss>")
    return "\n".join(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    state = {"items": {}, "status": {}}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    known = state["items"]
    status = {}
    failures = 0

    for key, name, url, fn in SOURCES:
        try:
            found = fn()
            for it in found:
                old = known.get(it["id"])
                it.update(source=key, source_name=name,
                          first_seen=old["first_seen"] if old else now.isoformat(),
                          last_seen=now.isoformat(), active=True)
                known[it["id"]] = it
            ids = {it["id"] for it in found}
            for k, v in known.items():
                if v["source"] == key and k not in ids:
                    v["active"] = False
            status[key] = {"ok": True, "count": len(found), "name": name, "url": url}
            print(f"[ok]   {key}: {len(found)} vagas")
        except Exception as e:  # mantém vagas antigas desta fonte
            failures += 1
            prev = state.get("status", {}).get(key, {})
            status[key] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300], "name": name,
                           "url": url, "count": prev.get("count", 0)}
            print(f"[erro] {key}: {e}", file=sys.stderr)
            traceback.print_exc()

    cutoff = now - dt.timedelta(days=FORGET_AFTER_DAYS)
    known = {k: v for k, v in known.items()
             if v.get("active") or dt.datetime.fromisoformat(v["last_seen"]) > cutoff}

    def sorted_items(filt):
        return sorted((v for v in known.values() if filt(v)),
                      key=lambda v: (v["first_seen"], v["id"]), reverse=True)

    # feeds mostram vagas ativas (as que estão no site agora)
    def write(fname, content):
        with open(os.path.join(OUT, fname), "w", encoding="utf-8") as f:
            f.write(content)

    base = SITE_URL
    write("feed.xml", rss("Vagas – todas as fontes", base or SOURCES[0][2],
                          f"{base}/feed.xml" if base else "",
                          sorted_items(lambda v: v.get("active"))))
    for key, name, url, _ in SOURCES:
        write(f"{key}.xml", rss(f"Vagas – {name}", url, f"{base}/{key}.xml" if base else "",
                                sorted_items(lambda v, k=key: v.get("active") and v["source"] == k)))

    state = {"items": known, "status": status,
             "updated": now.isoformat()}
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    write("index.html", index_html(status, now, base))
    print(f"Concluído. {failures} fonte(s) com erro.")


def index_html(status, now, base):
    local = now.astimezone(dt.timezone(dt.timedelta(hours=-3)))
    rows = []
    for key, name, url, _ in SOURCES:
        s = status.get(key, {})
        st = (f'<span class="ok">{s.get("count", 0)} vagas</span>' if s.get("ok")
              else '<span class="err">falhou na última coleta</span>')
        rows.append(f'<tr><td><a href="{escape(url)}">{escape(name)}</a></td><td>{st}</td>'
                    f'<td><a class="feed" href="{key}.xml">{key}.xml</a></td></tr>')
    return f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Feeds de Vagas</title>
<link rel="alternate" type="application/rss+xml" title="Vagas – todas as fontes" href="feed.xml">
<style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--line:#e3e2dc;--acc:#2a6f4e;--err:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--fg:#ecebe6;--mut:#a2a19b;--line:#2d2d2a;--acc:#6fcf9c;--err:#ff8a80}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:760px;margin:0 auto;padding:32px 16px}}
h1{{font-size:1.6rem;margin:0 0 4px}} p{{color:var(--mut)}}
.big{{display:block;padding:14px 16px;border:1px solid var(--line);border-radius:10px;
color:var(--acc);font-weight:600;text-decoration:none;word-break:break-all;margin:16px 0}}
table{{width:100%;border-collapse:collapse;margin-top:16px}}
td{{padding:10px 6px;border-top:1px solid var(--line);vertical-align:top}}
a{{color:var(--acc)}} .ok{{color:var(--mut)}} .err{{color:var(--err)}}
.feed{{font-family:ui-monospace,monospace;font-size:.9em}}
</style></head><body><main>
<h1>Feeds de Vagas</h1>
<p>Atualizado em {local:%d/%m/%Y %H:%M} (horário de Brasília). Coleta automática a cada 3 horas.</p>
<p>No Feedly, toque em <b>+</b> e cole o endereço abaixo para receber todas as vagas num só feed:</p>
<a class="big" href="feed.xml">{escape(base + '/feed.xml' if base else 'feed.xml')}</a>
<p>Ou assine cada fonte em separado:</p>
<table>{''.join(rows)}</table>
</main></body></html>"""


if __name__ == "__main__":
    main()
