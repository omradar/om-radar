#!/usr/bin/env python3
"""Génère de fausses données au format football-data.org pour tester le site sans clé.
Les équipes et résultats sont inventés. Ne jamais publier ces données."""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent / "sample"
OUT.mkdir(exist_ok=True)
random.seed(26)

TEAMS = [
    (1, "Paris Saint-Germain FC", "PSG"), (2, "Olympique de Marseille", "Marseille"),
    (3, "Olympique Lyonnais", "Lyon"), (4, "RC Lens", "Lens"), (5, "Lille OSC", "Lille"),
    (6, "Stade Rennais FC", "Rennes"), (7, "AS Monaco FC", "Monaco"), (8, "RC Strasbourg", "Strasbourg"),
    (9, "FC Lorient", "Lorient"), (10, "Toulouse FC", "Toulouse"), (11, "Stade Brestois 29", "Brest"),
    (12, "Paris FC", "Paris FC"), (13, "Angers SCO", "Angers"), (14, "Le Havre AC", "Le Havre"),
    (15, "OGC Nice", "Nice"), (16, "AJ Auxerre", "Auxerre"), (17, "FC Nantes", "Nantes"), (18, "FC Metz", "Metz"),
]
STRENGTH = {t[0]: s for t, s in zip(TEAMS, [2.2, 1.8, 1.6, 1.6, 1.5, 1.4, 1.4, 1.2, 1.0, 1.0, 1.0, 0.9, 0.8, 0.8, 0.8, 0.7, 0.6, 0.5])}
PLAYED = 8
TOTAL_DAYS = 34

ids = [t[0] for t in TEAMS]
rotation = ids[:]
fixtures = []
for day in range(1, TOTAL_DAYS + 1):
    r = rotation[:]
    pairs = [(r[i], r[-1 - i]) for i in range(len(r) // 2)]
    if day % 2 == 0:
        pairs = [(b, a) for a, b in pairs]
    fixtures.append((day, pairs))
    rotation = [rotation[0]] + [rotation[-1]] + rotation[1:-1]

base = datetime(2026, 8, 15, 19, 0, tzinfo=timezone.utc)
today_cut = PLAYED
matches = []
mid = 1000
for day, pairs in fixtures:
    for h, a in pairs:
        mid += 1
        when = base + timedelta(days=7 * (day - 1) + random.choice([0, 1, 1, 2]))
        finished = day <= today_cut
        m = {
            "id": mid, "utcDate": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "matchday": day,
            "status": "FINISHED" if finished else "TIMED",
            "homeTeam": {"id": h, "name": TEAMS[h - 1][1], "shortName": TEAMS[h - 1][2]},
            "awayTeam": {"id": a, "name": TEAMS[a - 1][1], "shortName": TEAMS[a - 1][2]},
            "score": {"fullTime": {"home": None, "away": None}},
        }
        if finished:
            lh = 1.4 * STRENGTH[h] / STRENGTH[a] ** 0.5 / 1.2
            la = 1.1 * STRENGTH[a] / STRENGTH[h] ** 0.5 / 1.2
            gh = min(6, int(random.gauss(lh, 1.0) + 0.5)) if lh > 0 else 0
            ga = min(6, int(random.gauss(la, 1.0) + 0.5)) if la > 0 else 0
            m["score"]["fullTime"] = {"home": max(0, gh), "away": max(0, ga)}
        matches.append(m)

table = {i: dict(won=0, draw=0, lost=0, gf=0, ga=0, played=0) for i in ids}
for m in matches:
    if m["status"] != "FINISHED":
        continue
    h, a = m["homeTeam"]["id"], m["awayTeam"]["id"]
    hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
    for t, gf, ga in ((h, hg, ag), (a, ag, hg)):
        r = table[t]
        r["played"] += 1
        r["gf"] += gf
        r["ga"] += ga
        r["won" if gf > ga else "draw" if gf == ga else "lost"] += 1
rows = sorted(ids, key=lambda i: (-(table[i]["won"] * 3 + table[i]["draw"]), -(table[i]["gf"] - table[i]["ga"]), -table[i]["gf"]))
standing_rows = []
for pos, i in enumerate(rows, 1):
    r = table[i]
    standing_rows.append({
        "position": pos, "team": {"id": i, "name": TEAMS[i - 1][1], "shortName": TEAMS[i - 1][2]},
        "playedGames": r["played"], "won": r["won"], "draw": r["draw"], "lost": r["lost"],
        "points": r["won"] * 3 + r["draw"], "goalsFor": r["gf"], "goalsAgainst": r["ga"],
        "goalDifference": r["gf"] - r["ga"]})

standings = {"season": {"startDate": "2026-08-14", "endDate": "2027-05-23", "currentMatchday": PLAYED},
             "standings": [{"type": "TOTAL", "table": standing_rows}]}

names = {2: ["Joueur Test A", "Joueur Test B", "Joueur Test C"], 1: ["Joueur Test D", "Joueur Test E"],
         3: ["Joueur Test F"], 4: ["Joueur Test G"], 5: ["Joueur Test H"], 7: ["Joueur Test I"]}
scorers = []
for tid, ns in names.items():
    for k, n in enumerate(ns):
        scorers.append({"player": {"name": n}, "team": {"id": tid, "name": TEAMS[tid - 1][1], "shortName": TEAMS[tid - 1][2]},
                        "goals": max(1, 7 - k * 2 - (tid % 3)), "assists": k + 1})
scorers.sort(key=lambda s: -s["goals"])

(OUT / "standings.json").write_text(json.dumps(standings, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "matches.json").write_text(json.dumps({"matches": matches}, ensure_ascii=False), encoding="utf-8")
(OUT / "scorers.json").write_text(json.dumps({"scorers": scorers}, ensure_ascii=False, indent=1), encoding="utf-8")
print("Données de test générées dans", OUT)
