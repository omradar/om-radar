#!/usr/bin/env python3
"""OM Radar : génère le site statique à partir de l'API football-data.org.

Usage :
    FOOTBALL_DATA_TOKEN=xxx python build.py          # vraies données, écrit dans dist/
    python build.py --sample                         # données factices de test, écrit dans dist-sample/

Si un appel à l'API échoue, le script s'arrête avec une erreur claire. Sur GitHub,
la version déjà en ligne reste alors publiée, rien n'est écrasé.
"""
import base64
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
API = "https://api.football-data.org/v4"
COMPETITION = "FL1"  # Ligue 1
TEAM_KEYWORD = "marseille"
PARIS = ZoneInfo("Europe/Paris")
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# ---------------------------------------------------------------- données

def api_get(path):
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        sys.exit("Erreur : la variable FOOTBALL_DATA_TOKEN est vide. Ajoute la clé dans les secrets GitHub.")
    req = urllib.request.Request(API + path, headers={"X-Auth-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        hint = {401: "clé refusée", 403: "cette ressource n'est pas incluse dans le plan gratuit",
                429: "trop d'appels, réessaie dans une minute"}.get(e.code, "erreur de l'API")
        sys.exit(f"Erreur API {e.code} sur {path} : {hint}.")
    except Exception as e:  # réseau, délai dépassé, JSON invalide
        sys.exit(f"Erreur réseau sur {path} : {type(e).__name__}.")


def load_data(sample):
    if sample:
        d = ROOT / "tests" / "sample"
        return tuple(json.loads((d / f).read_text(encoding="utf-8"))
                     for f in ("standings.json", "matches.json", "scorers.json"))
    standings = api_get(f"/competitions/{COMPETITION}/standings")
    matches = api_get(f"/competitions/{COMPETITION}/matches")
    scorers = api_get(f"/competitions/{COMPETITION}/scorers?limit=50")
    return standings, matches, scorers


UA = {"User-Agent": "Mozilla/5.0 (compatible; OM-Radar/1.0)"}
OM_RE = re.compile(r"marseill|\bOM\b|olympien|v[ée]lodrome|phoc[ée]en|commanderie", re.I)
MERCATO_RE = re.compile(r"mercato|transfert|recrue|\bpr[êe]t\b|signature|\bsigne\b|offre|piste|arriv[ée]e|d[ée]part|prolong|indemnit|\bcible\b", re.I)


def local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def http_get(url, limit=2_000_000, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(limit)


def http_post(url, data, timeout=15):
    headers = dict(UA)
    headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
    req = urllib.request.Request(url, data=data.encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(1_000_000).decode("utf-8", "ignore")


def https_url(url):
    """Les images en http seraient bloquées sur un site en https : on tente la version https."""
    url = (url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url if url.startswith("https://") else ""


def pretty_source(raw):
    """Un nom de média propre : « https://www.433foot.fr/ » devient « 433 Foot » (voir source_names dans config.json)."""
    raw = (raw or "").strip()
    host = ""
    if raw.startswith(("http://", "https://")):
        host = urllib.parse.urlparse(raw).netloc
    elif re.fullmatch(r"(www\.)?[\w-]+(\.[\w-]+)+", raw):
        host = raw
    if not host:
        return raw
    host = host.lower().removeprefix("www.")
    names = CONFIG.get("source_names", {})
    if host in names:
        return names[host]
    label = host.split(".")[0]
    return label.upper() if len(label) <= 3 else label.capitalize()


# ---- Google Actualités : le lien du flux est une redirection, on retrouve l'adresse réelle de l'article
# Méthode non officielle : si elle cesse de marcher, les articles concernés gardent simplement une lettre à la place de la photo.

def gn_token(link):
    p = urllib.parse.urlparse(link)
    parts = p.path.split("/")
    if p.netloc == "news.google.com" and len(parts) > 1 and parts[-2] in ("articles", "read"):
        return parts[-1]
    return ""


def gn_legacy(token):
    """Anciens identifiants : l'adresse de l'article est écrite dans l'identifiant lui-même."""
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("latin1")
    except Exception:
        return ""
    if raw.startswith("\x08\x13\x22"):
        raw = raw[3:]
    if raw.endswith("\xd2\x01\x00"):
        raw = raw[:-3]
    if not raw:
        return ""
    length = ord(raw[0])
    s = raw[2:length + 1] if length >= 0x80 else raw[1:length + 1]
    return s if s.startswith("http") else ""


def gn_parse_reply(text):
    """Extrait l'adresse de la réponse du serveur Google."""
    try:
        data = json.loads(text.split("\n\n")[1])[:-2]
        url = json.loads(data[0][2])[1]
        return url if isinstance(url, str) and url.startswith("http") else ""
    except Exception:
        return ""


def gn_resolve(token):
    """Adresse réelle de l'article, ou RuntimeError avec la raison (visible dans status.json)."""
    url = gn_legacy(token)
    if url:
        return url
    sg = ts = None
    title = ""
    for u in (f"https://news.google.com/articles/{token}", f"https://news.google.com/rss/articles/{token}"):
        page = http_get(u, limit=500_000, timeout=10).decode("utf-8", "ignore")
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if sg and ts:
            break
        t = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
        title = clean_html(t.group(1))[:60] if t else f"{len(page)} octets"
    if not (sg and ts):
        raise RuntimeError("page Google sans signature : " + title)
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
             f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{token}",{ts.group(1)},"{sg.group(1)}"]')
    body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner]]]))
    reply = http_post("https://news.google.com/_/DotsSplashUi/data/batchexecute", body)
    real = gn_parse_reply(reply)
    if not real:
        raise RuntimeError("réponse Google illisible : " + clean_html(reply)[:70])
    return real


# ---- détection automatique du flux RSS d'un site à partir de son adresse

def discover_feed(site):
    """Renvoie (adresse du flux, contenu) pour une page d'accueil, ou ('', b'')."""
    cands = []
    try:
        page = http_get(site, limit=400_000, timeout=12).decode("utf-8", "ignore")
        for tag in re.findall(r"<link\b[^>]*>", page, re.I):
            if re.search(r"type=[\"']application/(rss|atom)\+xml[\"']", tag, re.I):
                m = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.I)
                if m and "comment" not in m.group(1).lower():
                    cands.append(urllib.parse.urljoin(site, html.unescape(m.group(1))))
    except Exception:
        pass
    root = site if site.endswith("/") else site + "/"
    cands += [root + x for x in ("feed", "feed/", "rss", "rss.xml", "feed.xml", "flux-rss")]
    for u in dict.fromkeys(cands):
        try:
            raw = http_get(u, timeout=12)
        except Exception:
            continue
        head = raw[:200_000]
        if b"<item" in head or b"<entry" in head:
            return u, raw
    return "", b""


# ---- petit cache entre deux mises à jour (restauré par GitHub Actions), pour ne pas redemander les mêmes pages

CACHE_FILE = ROOT / "cache" / "news.json"


def load_cache():
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        now = time.time()
        return {k: v for k, v in data.items()
                if v.get("t", 0) > now - (6 * 3600 if v.get("fail") else 14 * 86400)}
    except Exception:
        return {}


def save_cache(cache):
    try:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[cache] non enregistré ({type(e).__name__})", file=sys.stderr)


def clean_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def child_text(el, *names):
    for c in el:
        if local(c.tag) in names and (c.text or "").strip():
            return c.text.strip()
    return ""


def find_image(el):
    """Image déclarée dans le flux : media:content, thumbnail, enclosure, ou balise img du texte."""
    for c in el.iter():
        n = local(c.tag)
        if n in ("content", "thumbnail", "enclosure"):
            url = https_url(c.get("url"))
            kind = c.get("type") or c.get("medium") or ""
            if url and (kind.startswith("image") or n == "thumbnail"
                        or re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I)):
                return url
    blob = " ".join((c.text or "") for c in el.iter() if local(c.tag) in ("description", "encoded", "summary", "content"))
    m = re.search(r"<img[^>]+src=[\"']((?:https?:)?//[^\"']+)[\"']", blob)
    return https_url(html.unescape(m.group(1))) if m else ""


def parse_date(text):
    from email.utils import parsedate_to_datetime
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def parse_feed(raw, src):
    root = ET.fromstring(raw)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = clean_html(child_text(el, "title"))
        link = child_text(el, "link")
        if not link:
            for c in el:
                if local(c.tag) == "link" and c.get("href") and c.get("rel", "alternate") == "alternate":
                    link = c.get("href")
                    break
        if not title or not link.startswith(("https://", "http://")):
            continue
        desc = clean_html(child_text(el, "description", "summary", "encoded", "content"))
        if src.get("only_om") and not OM_RE.search(title + " " + desc):
            continue
        source = src["name"]
        google = src.get("kind") == "google"
        if google:
            name = child_text(el, "source")
            if name:
                source = name
                bare = re.sub(r"^https?://(www\.)?", "", name).rstrip("/")
                for cand in (name, bare, pretty_source(name)):
                    if cand and title.lower().endswith(" - " + cand.lower()):
                        title = title[: -len(cand) - 3].rstrip()
                        break
            source = pretty_source(source)
            desc = ""
        cat = src.get("category", "Actualités")
        if cat == "auto":
            cat = "Mercato" if MERCATO_RE.search(title) else "Actualités"
        out.append({
            "title": title, "source": source, "category": cat, "link": link, "src": src["name"],
            "iso": parse_date(child_text(el, "pubdate", "published", "updated", "date")),
            "image": "" if google else find_image(el), "excerpt_raw": desc, "google": google})
        if len(out) >= src.get("max", 12):
            break
    return out


def og_image(url):
    try:
        page = http_get(url, limit=250_000, timeout=8).decode("utf-8", "ignore")
    except Exception:
        return ""
    for pat in (r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]*content=[\"']([^\"']+)",
                r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*(?:property|name)=[\"'](?:og:image|twitter:image)[\"']"):
        m = re.search(pat, page, re.I)
        if m:
            return https_url(html.unescape(m.group(1)))
    return ""


def make_excerpt(desc, title, limit):
    d = (desc or "").strip()
    if not d or limit <= 0:
        return ""
    if d.lower().startswith(title.lower()):
        d = d[len(title):].lstrip(" :-.")
    d = re.sub(r"(The post .*? appeared first on .*|Lire la suite.*|Continue reading.*|\[…\]|\[\.\.\.\])$", "", d, flags=re.I).strip()
    if len(d) < 40:
        return ""
    if len(d) > limit:
        d = d[:limit].rsplit(" ", 1)[0].rstrip(",;:. ") + "…"
    return d


def make_slug(title, link):
    base = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60].strip("-") or "article"
    return base + "-" + hashlib.sha1(link.encode()).hexdigest()[:6]


def sample_photo(i):
    """Fausse photo (dessin) pour tester la mise en page hors connexion."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675"><defs>'
           '<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1b6fb5"/>'
           '<stop offset="1" stop-color="#58BCEB"/></linearGradient></defs><rect width="1200" height="675" fill="url(#g)"/>'
           '<circle cx="900" cy="250" r="170" fill="#ffffff" fill-opacity=".18"/>'
           f'<text x="60" y="620" font-size="64" font-family="Arial" fill="#ffffff" fill-opacity=".85">PHOTO TEST {i + 1}</text></svg>')
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def load_news(sample):
    """Titres, source, image, court extrait et lien. Un flux en échec est ignoré, le compte rendu va dans le journal et dans status.json."""
    items, errors, feeds = [], {}, {}
    if sample:
        now = datetime.now(timezone.utc).isoformat()
        for i, (t, c) in enumerate([
                ("Titre d'exemple pour tester la mise en page", "Actualités"),
                ("Deuxième titre d'exemple, un peu plus long pour vérifier le retour à la ligne", "Actualités"),
                ("Troisième titre d'exemple", "Actualités"), ("Quatrième titre d'exemple", "Actualités"),
                ("Cinquième titre d'exemple", "Actualités"), ("Titre mercato d'exemple", "Mercato"),
                ("Autre titre mercato d'exemple", "Mercato"), ("Dernier titre d'exemple", "Actualités")]):
            items.append({"title": t, "source": "Source test", "category": c, "link": "https://example.com/" + str(i),
                          "src": "test", "iso": now, "google": False,
                          "image": sample_photo(i) if i in (0, 1, 2, 5) else "",
                          "excerpt_raw": "Court extrait d'exemple pour vérifier l'affichage du résumé sous le titre de l'article."})
    else:
        def fetch_source(src):
            try:
                if src.get("site") and not src.get("url"):
                    feed, raw = discover_feed(src["site"])
                    if not raw:
                        raise RuntimeError("aucun flux RSS trouvé sur ce site")
                else:
                    feed, raw = src["url"], http_get(src["url"])
                return src, feed, parse_feed(raw, src), ""
            except Exception as e:
                why = str(e) if isinstance(e, RuntimeError) else f"{type(e).__name__} {getattr(e, 'code', '')}".strip()
                return src, "", [], why

        active = [s for s in CONFIG.get("sources", []) if s.get("enabled", True)]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for src, feed, got, why in ex.map(fetch_source, active):
                if why:
                    errors[src["name"]] = why
                    print(f"[source] {src['name']} : ECHEC ({why})", file=sys.stderr)
                    continue
                feeds[src["name"]] = feed
                items += got

    seen, uniq = set(), []
    for n in items:
        key = re.sub(r"[^a-z0-9]+", "", n["title"].lower())
        if key in seen or n["link"] in seen:
            continue
        seen.add(key)
        seen.add(n["link"])
        n["orig"] = n["link"]
        uniq.append(n)
    uniq.sort(key=lambda n: n["iso"] or "", reverse=True)
    uniq = uniq[: CONFIG.get("max_news", 24)]

    resolved = 0
    if not CONFIG.get("images", True):
        for n in uniq:
            n["image"] = ""
    elif not sample:
        cache = load_cache()
        # 1) adresse réelle des articles qui arrivent par Google Actualités
        budget = CONFIG.get("google_resolve_max", 14)
        for n in uniq:
            tok = gn_token(n["link"]) if n["google"] else ""
            if not tok:
                continue
            ent = cache.get("g:" + tok)
            if ent is None:
                if budget <= 0:
                    continue
                budget -= 1
                try:
                    real, why = gn_resolve(tok), ""
                except Exception as e:
                    real = ""
                    why = str(e) if isinstance(e, RuntimeError) else f"{type(e).__name__} {getattr(e, 'code', '')}".strip()
                ent = cache["g:" + tok] = {"url": real, "t": time.time(), "fail": not real, "why": why}
                time.sleep(0.4)
            if ent["url"]:
                n["link"] = ent["url"]
                n["resolved"] = True
                resolved += 1
            else:
                n["gn_why"] = ent.get("why") or "non essayé (limite atteinte)"
        # un même article peut arriver par deux chemins : on garde le premier
        links, keep = set(), []
        for n in uniq:
            if n["link"] in links:
                continue
            links.add(n["link"])
            keep.append(n)
        uniq = keep
        # 2) photo de l'article (page de l'éditeur : image de partage)
        todo = [n for n in uniq if not n["image"] and (not n["google"] or n.get("resolved"))]

        def photo(n):
            ent = cache.get("i:" + n["link"])
            return ent["url"] if ent is not None else og_image(n["link"])

        with ThreadPoolExecutor(max_workers=6) as ex:
            for n, img in zip(todo, ex.map(photo, todo)):
                n["image"] = img
                cache.setdefault("i:" + n["link"], {"url": img, "t": time.time(), "fail": not img})
        save_cache(cache)

    limit = CONFIG.get("excerpt_chars", 160)
    for n in uniq:
        n["excerpt"] = make_excerpt(n.pop("excerpt_raw", ""), n["title"], limit)
        n["slug"] = make_slug(n["title"], n["orig"])

    stats = []
    for src in CONFIG.get("sources", []) if not sample else []:
        if not src.get("enabled", True):
            continue
        mine = [n for n in uniq if n["src"] == src["name"]]
        row = {"name": src["name"], "kept": len(mine), "with_image": sum(1 for n in mine if n["image"])}
        if src["name"] in feeds and src.get("site"):
            row["flux"] = feeds[src["name"]]
        if src.get("kind") == "google":
            row["adresse_reelle_trouvee"] = sum(1 for n in mine if n.get("resolved"))
            why = {}
            for n in mine:
                if n.get("gn_why"):
                    why[n["gn_why"]] = why.get(n["gn_why"], 0) + 1
            if why:
                row["echecs"] = why
        if src["name"] in errors:
            row["erreur"] = errors[src["name"]]
        stats.append(row)
        print(f"[source] {row}")
    counts = {}
    for n in uniq:
        counts[n["source"]] = counts.get(n["source"], 0) + 1
    names = [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:12]
    return uniq, names, stats


# ---------------------------------------------------------------- calculs

def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(PARIS)


def fmt_date(dt, with_time=True):
    s = f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month - 1]}"
    return s + (f" à {dt.hour:02d}h{dt.minute:02d}" if with_time else "")


def points(gf, ga):
    return 3 if gf > ga else 1 if gf == ga else 0


def team_stats(matches):
    """Statistiques par équipe, calculées sur les matchs terminés."""
    stats = {}
    finished = [m for m in matches if m["status"] == "FINISHED"
                and m["score"]["fullTime"]["home"] is not None]
    for m in sorted(finished, key=lambda x: x["utcDate"]):
        hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        for team, opp, gf, ga, venue in ((m["homeTeam"], m["awayTeam"], hg, ag, "home"),
                                         (m["awayTeam"], m["homeTeam"], ag, hg, "away")):
            s = stats.setdefault(team["id"], {
                "n": 0, "gf": 0, "ga": 0, "cs": 0, "results": [],
                "home": {"n": 0, "gf": 0, "ga": 0, "pts": 0},
                "away": {"n": 0, "gf": 0, "ga": 0, "pts": 0}})
            p = points(gf, ga)
            s["n"] += 1
            s["gf"] += gf
            s["ga"] += ga
            s["cs"] += 1 if ga == 0 else 0
            v = s[venue]
            v["n"] += 1
            v["gf"] += gf
            v["ga"] += ga
            v["pts"] += p
            s["results"].append({"letter": "w" if p == 3 else "d" if p == 1 else "l",
                                 "pts": p, "opp": opp.get("shortName") or opp["name"],
                                 "venue": venue, "gf": gf, "ga": ga, "date": m["utcDate"]})
    return stats


def metrics(s):
    """Six indicateurs bruts, plus grand = meilleur. None si pas de match joué."""
    if not s or s["n"] == 0:
        return None
    last5 = s["results"][-5:]
    return {
        "Attaque": s["gf"] / s["n"],
        "Défense": -s["ga"] / s["n"],
        "Forme": sum(r["pts"] for r in last5) / (3 * len(last5)),
        "Domicile": s["home"]["pts"] / s["home"]["n"] if s["home"]["n"] else None,
        "Extérieur": s["away"]["pts"] / s["away"]["n"] if s["away"]["n"] else None,
        "Solidité": s["cs"] / s["n"],
    }


AXES = ["Attaque", "Défense", "Forme", "Domicile", "Extérieur", "Solidité"]


def radar_values(stats, om_id):
    """Chaque indicateur est ramené de 0 (pire équipe) à 100 (meilleure équipe) de la Ligue 1."""
    all_m = {tid: metrics(s) for tid, s in stats.items()}
    all_m = {tid: m for tid, m in all_m.items() if m}
    if om_id not in all_m:
        return None
    om, avg = [], []
    for ax in AXES:
        vals = [m[ax] for m in all_m.values() if m[ax] is not None]
        if not vals or all_m[om_id][ax] is None:
            om.append(50)
            avg.append(50)
            continue
        lo, hi = min(vals), max(vals)
        norm = (lambda v: 50.0) if hi == lo else (lambda v: 100 * (v - lo) / (hi - lo))
        om.append(round(norm(all_m[om_id][ax])))
        avg.append(round(sum(norm(v) for v in vals) / len(vals)))
    return {"om": om, "avg": avg}


def poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def predict(stats, home_id, away_id):
    """Modèle de Poisson simple, buts marqués et encaissés à domicile et à l'extérieur."""
    sh = sum(s["home"]["gf"] for s in stats.values())
    nh = sum(s["home"]["n"] for s in stats.values())
    sa = sum(s["away"]["gf"] for s in stats.values())
    na = sum(s["away"]["n"] for s in stats.values())
    if nh == 0 or na == 0:
        return None
    avg_h, avg_a = sh / nh, sa / na
    k = 4  # poids de la moyenne de la ligue, utile en début de saison

    def rate(goals, n, avg):
        return (goals + avg * k) / (n + k)

    empty = {"home": {"n": 0, "gf": 0, "ga": 0}, "away": {"n": 0, "gf": 0, "ga": 0}}
    h = stats.get(home_id, empty)
    a = stats.get(away_id, empty)
    lam_h = avg_h * (rate(h["home"]["gf"], h["home"]["n"], avg_h) / avg_h) \
        * (rate(a["away"]["ga"], a["away"]["n"], avg_h) / avg_h)
    lam_a = avg_a * (rate(a["away"]["gf"], a["away"]["n"], avg_a) / avg_a) \
        * (rate(h["home"]["ga"], h["home"]["n"], avg_a) / avg_a)
    win = draw = lose = 0.0
    best, best_p = (1, 1), 0.0
    for i in range(0, 9):
        for j in range(0, 9):
            p = poisson(i, lam_h) * poisson(j, lam_a)
            if i > j:
                win += p
            elif i == j:
                draw += p
            else:
                lose += p
            if p > best_p:
                best, best_p = (i, j), p
    total = win + draw + lose
    w, d = round(100 * win / total), round(100 * draw / total)
    return {"home_win": w, "draw": d, "away_win": 100 - w - d,
            "lam_h": lam_h, "lam_a": lam_a, "score": best}


# ---------------------------------------------------------------- rendu

def esc(x):
    return html.escape(str(x), quote=True)


def radar_svg(vals):
    cx, cy, r = 200, 190, 130
    n = len(AXES)

    def pt(i, v):
        a = -math.pi / 2 + i * 2 * math.pi / n
        return cx + math.cos(a) * r * v / 100, cy + math.sin(a) * r * v / 100

    def poly(values):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, v in enumerate(values)))

    out = ['<svg class="radar" viewBox="0 0 400 380" role="img" '
           'aria-label="Radar du profil de jeu de l\'OM comparé à la moyenne de Ligue 1">']
    for lvl in (25, 50, 75, 100):
        out.append(f'<polygon points="{poly([lvl] * n)}" class="grid"/>')
    for i, name in enumerate(AXES):
        x, y = pt(i, 100)
        lx, ly = pt(i, 117)
        anchor = "middle" if abs(lx - cx) < 4 else ("start" if lx > cx else "end")
        out.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                   f'dominant-baseline="middle" class="axis">{esc(name)}</text>')
    out.append(f'<polygon points="{poly(vals["avg"])}" class="avg"/>')
    out.append(f'<polygon points="{poly(vals["om"])}" class="om"/>')
    for i, v in enumerate(vals["om"]):
        x, y = pt(i, v)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="dot"/>')
    out.append("</svg>")
    return "".join(out)


def dots(results):
    return '<span class="dots">' + "".join(
        f'<i class="{r["letter"]}" title="{esc(r["opp"])} {r["gf"]}-{r["ga"]}"></i>'
        for r in results[-5:]) + "</span>"


def rel_time(iso):
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if mins < 2:
        return "À l'instant"
    if mins < 60:
        return f"Il y a {mins} min"
    if mins < 60 * 24:
        return f"Il y a {mins // 60} h"
    if mins < 60 * 24 * 7:
        return f"Il y a {mins // (60 * 24)} j"
    d = dt.astimezone(PARIS)
    return f"{d.day} {MOIS[d.month - 1]}"


def initials(name):
    parts = [w for w in name.replace("-", " ").split() if w]
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper() if parts else "?"


def crest(team, small=False):
    name = team.get("shortName") or team["name"]
    url = team.get("crest") or ""
    cls = "crest sm" if small else "crest"
    fallback = esc(initials(name))
    if url.startswith("https://"):
        return (f'<span class="{cls}"><img src="{esc(url)}" alt="" loading="lazy" '
                f'onerror="this.replaceWith(document.createTextNode(\'{fallback}\'))"></span>')
    return f'<span class="{cls}">{fallback}</span>'


def standings_table(table, stats, om_id):
    rows = []
    for row in table:
        t = row["team"]
        cls = ' class="me"' if t["id"] == om_id else ""
        form = dots(stats.get(t["id"], {"results": []})["results"])
        rows.append(
            f'<tr{cls}><td class="num">{row["position"]}</td>'
            f'<td>{esc(t.get("shortName") or t["name"])}</td>'
            f'<td class="num"><b>{row["points"]}</b></td><td class="num">{row["playedGames"]}</td>'
            f'<td class="num">{row["goalDifference"]:+d}</td><td>{form}</td></tr>')
    return "\n".join(rows)


def fixture_rows(matches, om_id, finished):
    rows = []
    for m in matches:
        home = m["homeTeam"]["id"] == om_id
        opp = m["awayTeam"] if home else m["homeTeam"]
        name = esc(opp.get("shortName") or opp["name"])
        dt = parse_dt(m["utcDate"])
        venue = "Domicile" if home else "Extérieur"
        if finished:
            hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
            gf, ga = (hg, ag) if home else (ag, hg)
            letter = "w" if gf > ga else "d" if gf == ga else "l"
            right = f'<span class="score {letter}">{gf}-{ga}</span>'
            sub = f"J{m.get('matchday', '')}, {venue}, {dt.day}/{dt.month:02d}"
        else:
            right = f'<span class="d num">{dt.hour:02d}h{dt.minute:02d}</span>'
            sub = f"J{m.get('matchday', '')}, {venue}, {fmt_date(dt, False)}"
        rows.append(f'<li>{crest(opp, True)}<span>{name}<small>{sub}</small></span>{right}</li>')
    return "\n".join(rows)


def page_href(n, prefix):
    return f"{prefix}{n['slug']}.html"


def thumb_html(n, idx):
    letter = esc(initials(n["source"]))
    img = ""
    if n.get("image"):
        img = f'<img src="{esc(n["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
    return f'<div class="thumb t{idx % 4 + 1}" aria-hidden="true"><span>{letter}</span>{img}</div>'


def article_li(n, idx, prefix):
    p = f'<p>{esc(n["excerpt"])}</p>' if n.get("excerpt") else ""
    return (f'<li>{thumb_html(n, idx)}<div><span class="cat">{esc(n["category"])}</span>'
            f'<h3><a href="{esc(page_href(n, prefix))}">{esc(n["title"])}</a></h3>{p}'
            f'<div class="meta"><span>{esc(n["source"])}</span><span>{esc(rel_time(n["iso"]))}</span></div></div></li>')


def compact_li(n, idx, prefix):
    return (f'<li>{thumb_html(n, idx)}<div><span class="cat">{esc(n["category"])}</span>'
            f'<h3><a href="{esc(page_href(n, prefix))}">{esc(n["title"])}</a></h3>'
            f'<div class="meta"><span>{esc(n["source"])}</span><span>{esc(rel_time(n["iso"]))}</span></div></div></li>')


def hero_slide(n, idx):
    img = ""
    if n.get("image"):
        img = f'<img class="bg" src="{esc(n["image"])}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">'
    ex = f'<p>{esc(n["excerpt"])}</p>' if n.get("excerpt") else ""
    return (f'<article class="slide hero" aria-label="Actualité {idx + 1}">{img}<span class="big" aria-hidden="true">OM</span>'
            f'<span class="tag">{esc(n["category"])}</span>'
            f'<h1><a href="{esc(page_href(n, "actu/"))}">{esc(n["title"])}</a></h1>{ex}'
            f'<div class="meta"><span>{esc(n["source"])}</span><span>{esc(rel_time(n["iso"]))}</span></div></article>')


def fill(tpl, values):
    for k, v in values.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


def build_text(stats, om, finished, upcoming, pred):
    """Phrases générées à partir des chiffres, sans IA. Modèles simples et prudents."""
    out = []
    if finished:
        m = finished[-1]
        home = m["homeTeam"]["id"] == om["id"]
        opp = m["awayTeam"] if home else m["homeTeam"]
        hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        gf, ga = (hg, ag) if home else (ag, hg)
        verbe = "s'est imposé contre" if gf > ga else "a fait match nul face à" if gf == ga else "s'est incliné contre"
        lieu = "au Vélodrome" if home else "à l'extérieur"
        out.append(f"Lors de la dernière journée jouée, l'OM {verbe} {opp.get('shortName') or opp['name']} "
                   f"{lieu} ({gf}-{ga}).")
    s = stats.get(om["id"])
    if s and s["results"]:
        last5 = s["results"][-5:]
        pts = sum(r["pts"] for r in last5)
        out.append(f"Sur ses {len(last5)} derniers matchs, l'OM a pris {pts} points sur {3 * len(last5)} possibles, "
                   f"avec {sum(r['gf'] for r in last5)} buts marqués et {sum(r['ga'] for r in last5)} encaissés.")
    if upcoming and pred:
        m = upcoming[0]
        home = m["homeTeam"]["id"] == om["id"]
        opp = m["awayTeam"] if home else m["homeTeam"]
        p_om = pred["home_win"] if home else pred["away_win"]
        lieu_next = "à domicile" if home else "à l'extérieur"
        out.append(f"Prochain rendez-vous : {opp.get('shortName') or opp['name']}, "
                   f"{lieu_next}, {fmt_date(parse_dt(m['utcDate']))}. "
                   f"Le modèle donne {p_om} % de chances de victoire à l'OM.")
    return out


def match_title(m, om_id):
    home = m["homeTeam"]["id"] == om_id
    opp = m["awayTeam"] if home else m["homeTeam"]
    nm = esc(opp.get("shortName") or opp["name"])
    return f"OM contre {nm}" if home else f"{nm} contre OM"


def render(standings, matches_raw, scorers_raw, news, source_names, sample):
    matches = matches_raw["matches"]
    total = next(t for t in standings["standings"] if t["type"] == "TOTAL")["table"]
    om_row = next((r for r in total if TEAM_KEYWORD in r["team"]["name"].lower()), None)
    if om_row is None:
        sys.exit("Erreur : l'OM n'apparaît pas dans le classement de la compétition.")
    om = om_row["team"]
    stats = team_stats(matches)

    om_matches = [m for m in matches if om["id"] in (m["homeTeam"]["id"], m["awayTeam"]["id"])]
    finished = sorted([m for m in om_matches if m["status"] == "FINISHED"], key=lambda m: m["utcDate"])
    upcoming = sorted([m for m in om_matches if m["status"] in ("SCHEDULED", "TIMED")],
                      key=lambda m: m["utcDate"])
    radar = radar_values(stats, om["id"])
    pred = predict(stats, upcoming[0]["homeTeam"]["id"], upcoming[0]["awayTeam"]["id"]) if upcoming else None

    season = standings.get("season", {})
    start = (season.get("startDate") or "")[:4]
    end = (season.get("endDate") or "")[:4]
    season_label = f"{start}/{end[2:]}" if start and end else "saison en cours"

    # ----- prochain match
    if upcoming:
        m = upcoming[0]
        when = fmt_date(parse_dt(m["utcDate"]))
        title = match_title(m, om["id"])
        if pred:
            pw, pd, pl = pred["home_win"], pred["draw"], pred["away_win"]
            lab_l = esc(m["homeTeam"].get("shortName") or m["homeTeam"]["name"])
            lab_r = esc(m["awayTeam"].get("shortName") or m["awayTeam"]["name"])
            next_html = (
                f'<p class="when">J{m.get("matchday", "")} · {when}</p><h3>{title}</h3>'
                f'<div class="probs" role="img" aria-label="{lab_l} {pw} pour cent, nul {pd} pour cent, {lab_r} {pl} pour cent">'
                f'<div class="p-w" style="width:{max(pw, 9)}%">{pw}%</div>'
                f'<div class="p-d" style="width:{max(pd, 9)}%">{pd}%</div>'
                f'<div class="p-l" style="width:{max(pl, 9)}%">{pl}%</div></div>'
                f'<div class="probkey"><span>{lab_l}</span><span>Nul</span><span>{lab_r}</span></div>'
                f'<ul class="factors"><li><span>Buts attendus {lab_l}</span><b class="num">{pred["lam_h"]:.2f}</b></li>'
                f'<li><span>Buts attendus {lab_r}</span><b class="num">{pred["lam_a"]:.2f}</b></li>'
                f'<li><span>Score le plus probable</span><b class="num">{pred["score"][0]}-{pred["score"][1]}</b></li></ul>'
                f'<p class="note">Modèle simple (loi de Poisson) basé sur les buts marqués et encaissés de chaque équipe, '
                f'à domicile et à l\'extérieur. Il donne une tendance, pas une certitude.</p>')
        else:
            next_html = f'<p class="when">{when}</p><h3>{title}</h3><p class="note">Pas assez de matchs joués pour calculer des probabilités.</p>'
    else:
        next_html = '<p class="note">Aucun match à venir dans le calendrier pour le moment.</p>'

    # ----- carte dernier match
    if finished:
        m = finished[-1]
        hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        ht, at = m["homeTeam"], m["awayTeam"]
        dt = parse_dt(m["utcDate"])
        last_html = (
            '<div class="card-dark" id="dernier"><span class="label">Dernier match</span>'
            f'<div class="scoreboard"><div class="club">{crest(ht)}<span>{esc(ht.get("shortName") or ht["name"])}</span></div>'
            f'<div class="result num">{hg}-{ag}</div>'
            f'<div class="club">{crest(at)}<span>{esc(at.get("shortName") or at["name"])}</span></div></div>'
            f'<div class="meta"><span>Ligue 1</span><span>Journée {m.get("matchday", "")}</span><span>{fmt_date(dt, False)}</span></div>'
            f'<div class="formline"><span>Forme de l\'OM</span>{dots(stats.get(om["id"], {"results": []})["results"])}</div></div>')
    else:
        last_html = ('<div class="card-dark"><span class="label">Dernier match</span>'
                     '<p>Le championnat n\'a pas encore commencé.</p></div>')

    # ----- actualités : carrousel, listes
    pool = news[:20]
    slides = ([n for n in pool if n.get("image")] + [n for n in pool if not n.get("image")])[:5]
    used = {id(n) for n in slides}
    if slides:
        track = "".join(hero_slide(n, i) for i, n in enumerate(slides))
        ctrl = ""
        if len(slides) > 1:
            ctrl = ('<div class="ctrl"><button type="button" class="prev" aria-label="Actualité précédente">‹</button>'
                    f'<span class="count">1 / {len(slides)}</span>'
                    '<button type="button" class="next" aria-label="Actualité suivante">›</button></div>')
        hero_html = (f'<div class="hero-wrap" id="carousel" role="region" aria-roledescription="carrousel" aria-label="À la une">'
                     f'<div class="track">{track}</div>{ctrl}</div>')
    elif finished:
        m = finished[-1]
        hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        hero_html = (
            '<div class="hero-wrap"><article class="slide hero"><span class="big" aria-hidden="true">OM</span><span class="tag">Résultat</span>'
            f'<h1>{esc(m["homeTeam"].get("shortName") or m["homeTeam"]["name"])} {hg}-{ag} {esc(m["awayTeam"].get("shortName") or m["awayTeam"]["name"])}</h1>'
            f'<p>Journée {m.get("matchday", "")} de Ligue 1.</p></article></div>')
    else:
        hero_html = '<div class="hero-wrap"><article class="slide hero"><span class="tag">OM Radar</span><h1>La saison arrive</h1></article></div>'

    texts = build_text(stats, om, finished, upcoming, pred)
    text_html = "".join(f"<p>{esc(t)}</p>" for t in texts) or "<p>Le championnat n'a pas encore commencé.</p>"

    # « À la une » : à récence égale on montre d'abord les articles qui ont une photo
    cands = [n for n in news[:24] if id(n) not in used and n["category"] != "Mercato"]
    une_list = sorted(cands, key=lambda n: 0 if n.get("image") else 1)[:6]
    used |= {id(n) for n in une_list}
    mercato_list = [n for n in news if id(n) not in used and n["category"] == "Mercato"][:6]
    used |= {id(n) for n in mercato_list}
    latest_list = [n for n in news if id(n) not in used][:8]
    une_html = "".join(article_li(n, i, "actu/") for i, n in enumerate(une_list)) \
        or '<li class="empty">Aucun titre récupéré pour le moment.</li>'
    mercato_html = "".join(compact_li(n, i, "actu/") for i, n in enumerate(mercato_list)) \
        or '<li class="empty">Aucun titre mercato pour le moment.</li>'
    latest_html = "".join(compact_li(n, i, "actu/") for i, n in enumerate(latest_list)) \
        or '<li class="empty">Pas d\'autres titres pour le moment.</li>'

    # ----- buteurs
    scorers = scorers_raw.get("scorers", [])
    top = "".join(
        "<tr{}><td>{}</td><td>{}</td><td class=\"num\"><b>{}</b></td><td class=\"num\">{}</td></tr>".format(
            ' class="me"' if s["team"]["id"] == om["id"] else "",
            esc(s["player"]["name"]),
            esc(s["team"].get("shortName") or s["team"]["name"]),
            s.get("goals") or 0,
            s.get("assists") or 0)
        for s in scorers[:8])

    domain = CONFIG.get("domain", "").strip()
    base = ("https://" + domain) if domain else CONFIG.get("site_url", "").rstrip("/")
    now = datetime.now(PARIS)
    common = {
        "SEASON": esc(season_label),
        "POSITION": esc(om_row["position"]),
        "POINTS": esc(om_row["points"]),
        "PLAYED": esc(om_row["playedGames"]),
        "GOALS": f'{om_row["goalsFor"]}-{om_row["goalsAgainst"]}',
        "FORM": dots(stats.get(om["id"], {"results": []})["results"]),
        "UPDATED": fmt_date(now),
        "SAMPLE_BANNER": '<div class="banner">Données de test inventées. Ne pas publier.</div>' if sample else "",
        "SOURCES_LIST": "".join(f"<li>{esc(s)}</li>" for s in source_names) or "<li>Aucune source disponible</li>",
        "SOURCES_TEXT": esc(", ".join(source_names) or "presse en ligne"),
        "UPCOMING": fixture_rows(upcoming[:5], om["id"], False) or '<li class="empty">Calendrier indisponible.</li>',
        "NEXT": next_html,
        "TEXT": text_html,
    }
    idx_values = dict(common)
    idx_values.update({
        "ROOT": "", "HOME": "",
        "CANONICAL": f'<link rel="canonical" href="{esc(base)}/">' if base else "",
        "HERO": hero_html,
        "LASTMATCH": last_html,
        "UNE": une_html,
        "MERCATO": mercato_html,
        "LATEST": latest_html,
        "RADAR": radar_svg(radar) if radar else '<p class="note">Le radar apparaîtra après le premier match.</p>',
        "STANDINGS": standings_table(total, stats, om["id"]),
        "LAST": fixture_rows(list(reversed(finished))[:5], om["id"], True) or '<li class="empty">Aucun match joué.</li>',
        "SCORERS": top,
    })
    index_html = fill((ROOT / "templates" / "index.html").read_text(encoding="utf-8"), idx_values)

    # ----- pages d'articles
    art_tpl = (ROOT / "templates" / "article.html").read_text(encoding="utf-8")
    pages = {}
    for n in news:
        others = [o for o in news if o is not n][:6]
        fig = ""
        if n.get("image"):
            fig = (f'<figure class="artfig"><span class="ph">{esc(initials(n["source"]))}</span>'
                   f'<img src="{esc(n["image"])}" alt="" referrerpolicy="no-referrer" onerror="this.remove()"></figure>')
        lead = f'<p class="lead">{esc(n["excerpt"])}</p>' if n.get("excerpt") else ""
        desc = n.get("excerpt") or f"{n['title']} : résumé et lien vers {n['source']}, sur OM Radar."
        vals = dict(common)
        vals.update({
            "ROOT": "../", "HOME": "../index.html",
            "TITLE": esc(n["title"]), "DESC": esc(desc),
            "CANONICAL": f'<link rel="canonical" href="{esc(base)}/actu/{n["slug"]}.html">' if base else "",
            "CAT": esc(n["category"]), "SOURCE": esc(n["source"]), "WHEN": esc(rel_time(n["iso"])),
            "FIGURE": fig, "LEAD": lead, "LINK": esc(n["link"]),
            "RELATED": "".join(compact_li(o, i, "") for i, o in enumerate(others)) or '<li class="empty">Pas d\'autres titres.</li>',
        })
        pages[n["slug"]] = fill(art_tpl, vals)
    return index_html, pages, [n["slug"] for n in news], base


def annotate(stats, news):
    """Compte rendu visible dans l'onglet Actions de GitHub (annotations), pour voir quelles sources marchent."""
    def cmd(s):
        return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    rows = []
    for r in stats:
        bits = [f"{r['name']}: {r['kept']} articles, {r['with_image']} photos"]
        if r.get("flux"):
            bits.append("flux " + r["flux"])
        if r.get("adresse_reelle_trouvee") is not None:
            bits.append(f"adresses réelles {r['adresse_reelle_trouvee']}")
        if r.get("echecs"):
            bits.append("échecs " + json.dumps(r["echecs"], ensure_ascii=False))
        if r.get("erreur"):
            bits.append("ERREUR " + r["erreur"])
        rows.append(" ; ".join(bits))
    for i in range(0, len(rows), 4):
        bad = any("ERREUR" in x for x in rows[i:i + 4])
        print(f"::{'warning' if bad else 'notice'} title=Sources {i // 4 + 1}::" + cmd(" | ".join(rows[i:i + 4])))
    total, imgs = len(news), sum(1 for n in news if n.get("image"))
    print(f"::notice title=Résumé::{total} articles gardés, {imgs} avec photo")


def main():
    sample = "--sample" in sys.argv
    out = ROOT / ("dist-sample" if sample else "dist")
    standings, matches, scorers = load_data(sample)
    news, source_names, stats = load_news(sample)
    if not sample:
        annotate(stats, news)
    index_html, pages, slugs, base = render(standings, matches, scorers, news, source_names, sample)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "assets", out / "assets")
    (out / "index.html").write_text(index_html, encoding="utf-8")
    (out / "actu").mkdir()
    for slug, page in pages.items():
        (out / "actu" / f"{slug}.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    home = (base or "") + "/"
    (out / "404.html").write_text(
        '<!doctype html><html lang="fr"><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="3;url={html.escape(home)}">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Page introuvable | OM Radar</title>'
        '<body style="font-family:sans-serif;background:#0B1F33;color:#fff;text-align:center;padding:15vh 16px">'
        "<h1>Cet article n'est plus à la une</h1><p>Retour à l'accueil dans quelques secondes.</p>"
        f'<p><a style="color:#58BCEB" href="{html.escape(home)}">Aller tout de suite à OM Radar</a></p></body></html>',
        encoding="utf-8")
    if not sample:
        (out / "status.json").write_text(json.dumps(
            {"mis_a_jour": datetime.now(PARIS).isoformat(timespec="minutes"), "articles": len(news), "sources": stats},
            ensure_ascii=False, indent=1), encoding="utf-8")
    domain = CONFIG.get("domain", "").strip()
    if domain and not sample:
        (out / "CNAME").write_text(domain + "\n", encoding="utf-8")
    if base and not sample:
        urls = [base + "/"] + [f"{base}/actu/{s}.html" for s in slugs]
        (out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(f"<url><loc>{html.escape(u)}</loc></url>" for u in urls) + "\n</urlset>\n", encoding="utf-8")
        (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    print(f"Site généré dans {out.name}/ ({len(index_html) // 1024} Ko, {len(pages)} pages d'articles)")


if __name__ == "__main__":
    main()
