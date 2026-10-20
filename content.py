"""Contenus propres à OM Radar, générés à partir des chiffres : dates, rangs, textes d'analyse, visuels SVG.

Rien ici n'appelle Internet. Tout part des données déjà récupérées par build.py.
"""
import html
import math
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

NAVY, ELECTRIC, SKY, MIST = "#0B1F33", "#0085FF", "#58BCEB", "#EAF2F7"
HEAD_FONT = "Barlow Condensed, Arial Narrow, Impact, sans-serif"


def esc(x):
    return html.escape(str(x), quote=True)


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(PARIS)


def fmt_date(dt, with_time=True):
    s = f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month - 1]}"
    return s + (f" à {dt.hour:02d}h{dt.minute:02d}" if with_time else "")


def ord_fr(n):
    return "1er" if n == 1 else f"{n}e"


def num(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def short(team):
    return team.get("shortName") or team["name"]


def initials(name):
    parts = [w for w in name.replace("-", " ").split() if w]
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper() if parts else "?"


# ------------------------------------------------------------------ rangs

def _last5_ratio(s):
    r = s["results"][-5:]
    return sum(x["pts"] for x in r) / (3 * len(r)) if r else None


AXES_DEF = [
    ("Attaque", True, lambda s: s["gf"] / s["n"],
     lambda s: f"{num(s['gf'] / s['n'])} but marqué par match"),
    ("Défense", False, lambda s: s["ga"] / s["n"],
     lambda s: f"{num(s['ga'] / s['n'])} but encaissé par match"),
    ("Forme", True, _last5_ratio,
     lambda s: f"{sum(x['pts'] for x in s['results'][-5:])} points sur {3 * len(s['results'][-5:])} lors des derniers matchs"),
    ("Domicile", True, lambda s: s["home"]["pts"] / s["home"]["n"] if s["home"]["n"] else None,
     lambda s: f"{s['home']['pts']} points en {s['home']['n']} match(s) à domicile"),
    ("Extérieur", True, lambda s: s["away"]["pts"] / s["away"]["n"] if s["away"]["n"] else None,
     lambda s: f"{s['away']['pts']} points en {s['away']['n']} match(s) à l'extérieur"),
    ("Solidité", True, lambda s: s["cs"] / s["n"],
     lambda s: f"{round(100 * s['cs'] / s['n'])} % de matchs sans but encaissé"),
]


def axis_details(stats, team_id):
    """Pour chaque axe : texte chiffré et rang parmi les équipes ayant joué."""
    s = stats.get(team_id)
    if not s or s["n"] == 0:
        return []
    out = []
    for name, higher_better, fn, label in AXES_DEF:
        vals = {}
        for tid, st in stats.items():
            if st["n"] == 0:
                continue
            try:
                v = fn(st)
            except ZeroDivisionError:
                v = None
            if v is not None:
                vals[tid] = v
        if team_id not in vals:
            continue
        me = vals[team_id]
        better = sum(1 for v in vals.values() if (v > me if higher_better else v < me))
        out.append({"name": name, "text": label(s), "rank": better + 1, "total": len(vals)})
    return out


def streak_text(results):
    """Série en cours la plus parlante, ou chaîne vide."""
    def run(cond):
        n = 0
        for r in reversed(results):
            if cond(r):
                n += 1
            else:
                break
        return n
    w, u, l, nw = run(lambda r: r["pts"] == 3), run(lambda r: r["pts"] > 0), \
        run(lambda r: r["pts"] == 0), run(lambda r: r["pts"] < 3)
    if w >= 2:
        return f"{w} victoires de suite"
    if u >= 3:
        return f"invaincu depuis {u} matchs"
    if l >= 2:
        return f"{l} défaites de suite"
    if nw >= 3:
        return f"{nw} matchs sans victoire"
    return ""


# ------------------------------------------------------------------ visuels SVG

def _rings(cx, cy, opacity=0.35):
    return "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c}" stroke-width="{w}" opacity="{o}"/>'
        for r, c, w, o in ((70, SKY, 5, opacity), (110, SKY, 5, opacity * 0.65), (150, ELECTRIC, 5, opacity * 0.8)))


def _club(cx, text):
    return (f'<circle cx="{cx}" cy="168" r="50" fill="#fff"/>'
            f'<text x="{cx}" y="182" text-anchor="middle" font-size="40" font-weight="800" '
            f'font-family="{HEAD_FONT}" fill="{NAVY}">{esc(text)}</text>')


def match_visual(left, right, center, label, sub, alt):
    """Visuel 16:9 d'un match : deux pastilles, score ou VS, étiquette. 100 % original."""
    return (
        f'<svg class="vis" viewBox="0 0 640 360" role="img" aria-label="{esc(alt)}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="640" height="360" fill="{NAVY}"/>{_rings(520, 70)}{_rings(80, 330, 0.2)}'
        f'<rect x="28" y="26" width="{18 + 13 * len(label)}" height="34" rx="3" fill="{ELECTRIC}"/>'
        f'<text x="40" y="50" font-size="22" font-weight="700" letter-spacing="1.5" font-family="{HEAD_FONT}" fill="#fff">{esc(label.upper())}</text>'
        f'{_club(130, initials(left))}{_club(510, initials(right))}'
        f'<text x="320" y="196" text-anchor="middle" font-size="96" font-weight="800" font-family="{HEAD_FONT}" fill="#fff">{esc(center)}</text>'
        f'<text x="130" y="258" text-anchor="middle" font-size="26" font-weight="700" font-family="{HEAD_FONT}" fill="{SKY}">{esc(left.upper())}</text>'
        f'<text x="510" y="258" text-anchor="middle" font-size="26" font-weight="700" font-family="{HEAD_FONT}" fill="{SKY}">{esc(right.upper())}</text>'
        f'<text x="28" y="334" font-size="22" font-weight="600" font-family="{HEAD_FONT}" fill="#bcd4e6">{esc(sub)}</text>'
        f'<text x="612" y="334" text-anchor="end" font-size="26" font-weight="800" letter-spacing="2" font-family="{HEAD_FONT}" fill="#fff">OM <tspan fill="{SKY}">RADAR</tspan></text>'
        f'</svg>')


def radar_visual(vals, label, sub, alt):
    cx, cy, r, n = 470, 185, 118, 6

    def pt(i, v):
        a = -math.pi / 2 + i * 2 * math.pi / n
        return cx + math.cos(a) * r * v / 100, cy + math.sin(a) * r * v / 100

    def poly(values):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, v in enumerate(values)))

    grid = "".join(f'<polygon points="{poly([lvl] * n)}" fill="none" stroke="#fff" stroke-opacity="0.2"/>' for lvl in (33, 66, 100))
    return (
        f'<svg class="vis" viewBox="0 0 640 360" role="img" aria-label="{esc(alt)}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="640" height="360" fill="{NAVY}"/>{grid}'
        f'<polygon points="{poly(vals["avg"])}" fill="none" stroke="#9db3c4" stroke-width="2" stroke-dasharray="5 4"/>'
        f'<polygon points="{poly(vals["om"])}" fill="{ELECTRIC}" fill-opacity="0.4" stroke="{SKY}" stroke-width="4"/>'
        f'<rect x="28" y="26" width="{18 + 13 * len(label)}" height="34" rx="3" fill="{ELECTRIC}"/>'
        f'<text x="40" y="50" font-size="22" font-weight="700" letter-spacing="1.5" font-family="{HEAD_FONT}" fill="#fff">{esc(label.upper())}</text>'
        f'<text x="28" y="170" font-size="84" font-weight="800" font-family="{HEAD_FONT}" fill="#fff">PROFIL</text>'
        f'<text x="28" y="240" font-size="84" font-weight="800" font-family="{HEAD_FONT}" fill="{SKY}">DE JEU</text>'
        f'<text x="28" y="334" font-size="22" font-weight="600" font-family="{HEAD_FONT}" fill="#bcd4e6">{esc(sub)}</text>'
        f'<text x="612" y="334" text-anchor="end" font-size="26" font-weight="800" letter-spacing="2" font-family="{HEAD_FONT}" fill="#fff">OM <tspan fill="{SKY}">RADAR</tspan></text>'
        f'</svg>')


# ------------------------------------------------------------------ articles

def _score_for_om(m, om_id):
    home = m["homeTeam"]["id"] == om_id
    hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
    return (hg, ag) if home else (ag, hg), home


def after_match_article(ctx):
    """Analyse chiffrée du dernier match joué par l'OM. None si aucun match."""
    om, stats, finished = ctx["om"], ctx["stats"], ctx["finished"]
    if not finished:
        return None
    m = finished[-1]
    (gf, ga), home = _score_for_om(m, om["id"])
    ht, at = m["homeTeam"], m["awayTeam"]
    opp = at if home else ht
    dt = parse_dt(m["utcDate"])
    hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
    verb = "s'impose" if gf > ga else "fait match nul" if gf == ga else "s'incline"
    prep = "contre" if gf >= ga and gf != ga else "face à" if gf == ga else "contre"
    where = "au Vélodrome" if home else "à l'extérieur"
    title = f"{short(ht)} {hg}-{ag} {short(at)} : l'analyse chiffrée"
    chapo = (f"L'OM {verb} {prep if gf != ga else 'face à'} {short(opp)} {where} ({gf}-{ga}) lors de la "
             f"{ord_fr(m.get('matchday') or 0)} journée de Ligue 1, {fmt_date(dt, False)}.")
    s = stats.get(om["id"])
    paras = []
    p1 = f"{chapo[:-1]}."
    if s and len(s["results"]) > 1:
        best = max(r["gf"] for r in s["results"])
        worst = min(r["ga"] for r in s["results"])
        if gf == best and gf >= 3:
            p1 += f" Avec {gf} buts marqués, c'est son plus gros total offensif de la saison."
        if ga == 0 and ga == worst:
            p1 += " L'OM n'a pas encaissé de but."
        elif ga >= 3:
            p1 += f" Il a en revanche encaissé {ga} buts."
    paras.append(p1)

    row = ctx["om_row"]
    leader = ctx["table"][0]
    gap = leader["points"] - row["points"]
    p2 = (f"Au classement, l'OM occupe la {ord_fr(row['position'])} place avec {row['points']} points en "
          f"{row['playedGames']} matchs ({row['won']} victoires, {row['draw']} nuls, {row['lost']} défaites).")
    if gap > 0:
        p2 += f" Le leader, {short(leader['team'])}, compte {gap} point{'s' if gap > 1 else ''} de plus."
    else:
        p2 += " L'OM est leader du championnat."
    paras.append(p2)

    if s and s["results"]:
        last5 = s["results"][-5:]
        pts = sum(r["pts"] for r in last5)
        p3 = (f"Sur les {len(last5)} derniers matchs, l'OM a pris {pts} points sur {3 * len(last5)}, avec "
              f"{sum(r['gf'] for r in last5)} buts marqués et {sum(r['ga'] for r in last5)} encaissés.")
        st = streak_text(s["results"])
        if st:
            p3 += f" Série en cours : {st}."
        paras.append(p3)

    details = {d["name"]: d for d in axis_details(stats, om["id"])}
    if "Attaque" in details and "Défense" in details:
        a, d = details["Attaque"], details["Défense"]
        paras.append(f"Sur la saison, l'attaque marseillaise est la {ord_fr(a['rank'])} de Ligue 1 "
                     f"({a['text']}) et la défense la {ord_fr(d['rank'])} ({d['text']}).")

    om_sc = [(i, x) for i, x in enumerate(ctx["scorers"], 1) if x["team"]["id"] == om["id"]]
    if om_sc:
        i, x = om_sc[0]
        goals = x.get("goals") or 0
        paras.append(f"Meilleur buteur marseillais du classement : {x['player']['name']}, "
                     f"{goals} but{'s' if goals > 1 else ''} ({ord_fr(i)} des buteurs de Ligue 1).")

    visual = match_visual(short(ht), short(at), f"{hg}-{ag}", "Après-match",
                          f"Journée {m.get('matchday', '')}, {fmt_date(dt, False)}",
                          f"{short(ht)} {hg}-{ag} {short(at)}")
    return {"slug": "apres-match", "kicker": "Après-match", "title": title, "chapo": chapo, "paras": paras,
            "visual": visual, "date": dt, "big": f"{hg}-{ag}"}


def before_match_article(ctx):
    """Avant-match : probabilités et comparaison des formes. None s'il n'y a pas de match à venir."""
    om, stats, upcoming, pred = ctx["om"], ctx["stats"], ctx["upcoming"], ctx["pred"]
    if not upcoming:
        return None
    m = upcoming[0]
    home = m["homeTeam"]["id"] == om["id"]
    opp = m["awayTeam"] if home else m["homeTeam"]
    dt = parse_dt(m["utcDate"])
    ht, at = m["homeTeam"], m["awayTeam"]
    title_core = f"OM - {short(opp)}" if home else f"{short(opp)} - OM"
    title = f"{title_core} : les chiffres avant le coup d'envoi"
    lieu = "au Vélodrome" if home else f"chez {short(opp)}"
    chapo = f"{ord_fr(m.get('matchday') or 0)} journée de Ligue 1, {fmt_date(dt)}, {lieu}."
    paras = [chapo]
    if pred:
        p_om = pred["home_win"] if home else pred["away_win"]
        p_opp = pred["away_win"] if home else pred["home_win"]
        s1, s2 = pred["score"]
        paras.append(f"Le modèle donne {p_om} % de chances de victoire à l'OM, {pred['draw']} % pour le nul et "
                     f"{p_opp} % pour {short(opp)}. Buts attendus : {num(pred['lam_h'])} pour {short(ht)} et "
                     f"{num(pred['lam_a'])} pour {short(at)}. Le score le plus probable est {s1}-{s2}.")
        tops = ", ".join(f"{a}-{b} ({p} %)" for a, b, p in pred.get("top", [])[:3])
        if tops:
            paras.append(f"Les trois scores les plus probables : {tops}.")
    so, sp = stats.get(om["id"]), stats.get(opp["id"])
    row_opp = next((r for r in ctx["table"] if r["team"]["id"] == opp["id"]), None)
    if so and sp and so["results"] and sp["results"]:
        po = sum(r["pts"] for r in so["results"][-5:])
        pp = sum(r["pts"] for r in sp["results"][-5:])
        p = (f"Forme comparée : l'OM a pris {po} points sur ses {min(5, len(so['results']))} derniers matchs, "
             f"{short(opp)} en a pris {pp} sur {min(5, len(sp['results']))}.")
        if row_opp:
            p += f" {short(opp)} est {ord_fr(row_opp['position'])} au classement avec {row_opp['points']} points."
        paras.append(p)
    if so and sp:
        if home and so["home"]["n"] and sp["away"]["n"]:
            paras.append(f"À domicile, l'OM a pris {so['home']['pts']} points en {so['home']['n']} matchs. "
                         f"À l'extérieur, {short(opp)} en a pris {sp['away']['pts']} en {sp['away']['n']}.")
        elif not home and so["away"]["n"] and sp["home"]["n"]:
            paras.append(f"À l'extérieur, l'OM a pris {so['away']['pts']} points en {so['away']['n']} matchs. "
                         f"À domicile, {short(opp)} en a pris {sp['home']['pts']} en {sp['home']['n']}.")
    visual = match_visual(short(ht), short(at), "VS", "Avant-match",
                          f"Journée {m.get('matchday', '')}, {fmt_date(dt)}",
                          f"{short(ht)} contre {short(at)}")
    return {"slug": "avant-match", "kicker": "Avant-match", "title": title, "chapo": chapo, "paras": paras,
            "visual": visual, "date": dt, "big": "VS", "pred_box": True}


def radar_article(ctx):
    """Le profil de jeu de l'OM, axe par axe. None si le radar n'existe pas encore."""
    om, stats, radar = ctx["om"], ctx["stats"], ctx["radar"]
    if not radar:
        return None
    details = axis_details(stats, om["id"])
    if not details:
        return None
    best = min(details, key=lambda d: d["rank"])
    worst = max(details, key=lambda d: d["rank"])
    chapo = (f"Point fort de l'OM : {best['name'].lower()} ({ord_fr(best['rank'])} de Ligue 1). "
             f"Point à travailler : {worst['name'].lower()} ({ord_fr(worst['rank'])}).")
    paras = [chapo, "Chaque axe du radar va de 0 (la pire équipe de Ligue 1 sur cet indicateur) à 100 (la meilleure). "
             "La ligne pointillée représente la moyenne du championnat."]
    now = datetime.now(PARIS)
    visual = radar_visual(radar, "Analyse", f"{ctx['om_row']['playedGames']} matchs joués",
                          "Radar du profil de jeu de l'OM")
    return {"slug": "profil-de-jeu", "kicker": "Analyse", "title": "Le profil de jeu de l'OM, axe par axe",
            "chapo": chapo, "paras": paras, "visual": visual, "date": now, "big": "RADAR",
            "axes": details, "radar_box": True}


def build_articles(ctx):
    arts = [after_match_article(ctx), before_match_article(ctx), radar_article(ctx)]
    return [a for a in arts if a]
