#!/usr/bin/env python3
"""OM Radar : génère le site statique à partir de l'API football-data.org.

Usage :
    FOOTBALL_DATA_TOKEN=xxx python build.py          # vraies données, écrit dans dist/
    python build.py --sample                         # données factices de test, écrit dans dist-sample/

Si un appel à l'API échoue, le script s'arrête avec une erreur claire. Sur GitHub,
la version déjà en ligne reste alors publiée, rien n'est écrasé.
"""
import html
import json
import math
import os
import shutil
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
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


def load_news(sample):
    """Titres, source, catégorie et lien uniquement. Un flux en échec est ignoré."""
    if sample:
        now = datetime.now(timezone.utc).isoformat()
        return [
            {"title": "Titre d'exemple pour tester la mise en page", "source": "Source test", "category": "Actualités", "link": "https://example.com", "iso": now},
            {"title": "Deuxième titre d'exemple, un peu plus long pour vérifier le retour à la ligne", "source": "Source test", "category": "Actualités", "link": "https://example.com", "iso": now},
            {"title": "Troisième titre d'exemple", "source": "Source test", "category": "Actualités", "link": "https://example.com", "iso": now},
            {"title": "Quatrième titre d'exemple", "source": "Source test", "category": "Actualités", "link": "https://example.com", "iso": now},
            {"title": "Titre mercato d'exemple", "source": "Source test", "category": "Mercato", "link": "https://example.com", "iso": now},
            {"title": "Autre titre mercato d'exemple", "source": "Source test", "category": "Mercato", "link": "https://example.com", "iso": now},
        ]
    from email.utils import parsedate_to_datetime
    items, seen = [], set()
    for feed in CONFIG.get("feeds", []):
        try:
            req = urllib.request.Request(feed["url"], headers={"User-Agent": "OM-Radar/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                root = ET.fromstring(resp.read())
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                if not title or not link.startswith("http"):
                    continue
                src = (it.findtext("source") or feed["name"]).strip()
                if title.endswith(" - " + src):
                    title = title[: -len(src) - 3]
                key = title.lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    iso = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
                except Exception:
                    iso = ""
                items.append({"title": title, "source": src, "category": feed.get("category", "Actualités"),
                              "link": link, "iso": iso})
        except Exception as e:
            print(f"Veille ignorée pour {feed.get('name')} : {type(e).__name__}", file=sys.stderr)
    items.sort(key=lambda n: n["iso"], reverse=True)
    return items


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


def article_li(n, idx, summary=""):
    letter = esc(initials(n["source"]))
    p = f"<p>{esc(summary)}</p>" if summary else ""
    return (f'<li><div class="thumb t{idx % 4 + 1}" aria-hidden="true">{letter}</div><div>'
            f'<span class="cat">{esc(n["category"])}</span>'
            f'<h3><a href="{esc(n["link"])}" target="_blank" rel="noopener">{esc(n["title"])}</a></h3>{p}'
            f'<div class="meta"><span>{esc(n["source"])}</span><span>{esc(rel_time(n["iso"]))}</span></div></div></li>')


def compact_li(n, idx):
    letter = esc(initials(n["source"]))
    return (f'<li><div class="thumb t{idx % 4 + 1}" aria-hidden="true">{letter}</div><div>'
            f'<span class="cat">{esc(n["category"])}</span>'
            f'<h3><a href="{esc(n["link"])}" target="_blank" rel="noopener">{esc(n["title"])}</a></h3>'
            f'<div class="meta"><span>{esc(n["source"])}</span><span>{esc(rel_time(n["iso"]))}</span></div></div></li>')


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


def render(standings, matches_raw, scorers_raw, news, sample):
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
    matchday = season.get("currentMatchday") or (finished[-1].get("matchday") if finished else 0)
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

    # ----- actualités
    une_news = [n for n in news if n["category"] != "Mercato"]
    mercato_news = [n for n in news if n["category"] == "Mercato"]
    hero_item = une_news[0] if une_news else (mercato_news[0] if mercato_news else None)
    rest = [n for n in news if n is not hero_item]
    if hero_item:
        hero_html = (
            '<article class="hero"><span class="big" aria-hidden="true">OM</span>'
            f'<span class="tag">{esc(hero_item["category"])}</span>'
            f'<h1><a href="{esc(hero_item["link"])}" target="_blank" rel="noopener">{esc(hero_item["title"])}</a></h1>'
            f'<div class="meta"><span>{esc(hero_item["source"])}</span><span>{esc(rel_time(hero_item["iso"]))}</span></div>'
            '<div class="arrows" aria-hidden="true"><span>‹</span><span>›</span></div></article>')
    elif finished:
        m = finished[-1]
        hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        hero_html = (
            '<article class="hero"><span class="big" aria-hidden="true">OM</span><span class="tag">Résultat</span>'
            f'<h1>{esc(m["homeTeam"].get("shortName") or m["homeTeam"]["name"])} {hg}-{ag} {esc(m["awayTeam"].get("shortName") or m["awayTeam"]["name"])}</h1>'
            f'<p>Journée {m.get("matchday", "")} de Ligue 1.</p></article>')
    else:
        hero_html = '<article class="hero"><span class="tag">OM Radar</span><h1>La saison arrive</h1></article>'

    texts = build_text(stats, om, finished, upcoming, pred)
    text_html = "".join(f"<p>{esc(t)}</p>" for t in texts) or "<p>Le championnat n'a pas encore commencé.</p>"

    une_list = [n for n in rest if n["category"] != "Mercato"][:6]
    une_html = "".join(article_li(n, i, texts[i] if (i == 0 and texts) else "") for i, n in enumerate(une_list)) \
        or '<li class="empty">Aucun titre récupéré pour le moment.</li>'
    mercato_html = "".join(compact_li(n, i) for i, n in enumerate(mercato_news[:6])) \
        or '<li class="empty">Aucun titre mercato pour le moment.</li>'
    used = {id(n) for n in une_list} | {id(n) for n in mercato_news[:6]} | {id(hero_item)}
    latest_html = "".join(compact_li(n, i) for i, n in enumerate([n for n in news if id(n) not in used][:8])) \
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

    form = dots(stats.get(om["id"], {"results": []})["results"])
    now = datetime.now(PARIS)
    tpl = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    values = {
        "SEASON": esc(season_label),
        "POSITION": esc(om_row["position"]),
        "POINTS": esc(om_row["points"]),
        "PLAYED": esc(om_row["playedGames"]),
        "GOALS": f'{om_row["goalsFor"]}-{om_row["goalsAgainst"]}',
        "FORM": form,
        "HERO": hero_html,
        "LASTMATCH": last_html,
        "UNE": une_html,
        "MERCATO": mercato_html,
        "LATEST": latest_html,
        "RADAR": radar_svg(radar) if radar else '<p class="note">Le radar apparaîtra après le premier match.</p>',
        "NEXT": next_html,
        "TEXT": text_html,
        "STANDINGS": standings_table(total, stats, om["id"]),
        "LAST": fixture_rows(list(reversed(finished))[:5], om["id"], True) or '<li class="empty">Aucun match joué.</li>',
        "UPCOMING": fixture_rows(upcoming[:5], om["id"], False) or '<li class="empty">Calendrier indisponible.</li>',
        "SCORERS": top,
        "UPDATED": fmt_date(now),
        "SAMPLE_BANNER": '<div class="banner">Données de test inventées. Ne pas publier.</div>' if sample else "",
    }
    for k, v in values.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


def main():
    sample = "--sample" in sys.argv
    out = ROOT / ("dist-sample" if sample else "dist")
    standings, matches, scorers = load_data(sample)
    news = load_news(sample)
    page = render(standings, matches, scorers, news, sample)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "assets", out / "assets")
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Site généré dans {out.name}/ ({len(page) // 1024} Ko)")


if __name__ == "__main__":
    main()
