import html
import json
import sqlite3
import re
import unicodedata
import math
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "scripts" / "football_data.sqlite"
OUT = ROOT / "index.html"

def pct(value):
    return "—" if value is None else f"{value:.0f}%"

def result_percentages(values):
    total = sum(values)
    raw = [value / total * 100 for value in values]
    whole = [math.floor(value) for value in raw]
    for index in sorted(range(3), key=lambda i: raw[i] - whole[i], reverse=True)[:100 - sum(whole)]:
        whole[index] += 1
    return [f"{value}%" for value in whole]

def norm(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\b(fc|cf|ac|afc|fk|sc|the)\b", " ", value)
    return re.sub(r"[^a-z0-9]", "", value)

def canonical_season(season):
    digits = "".join(ch for ch in season if ch.isdigit())
    return f"20{digits[:2]}/20{digits[2:4]}" if len(digits) == 4 and len(season) == 4 and not digits.startswith("20") else season

def season_rank(season):
    digits = "".join(ch for ch in season if ch.isdigit())
    return int(digits[:4] or 0)

def date_rank(value):
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except (TypeError, ValueError):
        return datetime.min

def form(games, team, at_home):
    output = []
    scored = conceded = 0
    for _, _, _, _, home, away, hg, ag in sorted(games, key=lambda row: date_rank(row[3]), reverse=True)[:5]:
        own, opp = (hg, ag) if at_home else (ag, hg)
        scored += own; conceded += opp
        output.append("W" if own > opp else "D" if own == opp else "L")
    return " ".join(output) or "No recent matches", scored, conceded

def main():
    con = sqlite3.connect(DB)
    rows = con.execute("""
      SELECT l.country, l.competition, l.home_team, l.away_team,
             p.matches_used, p.home_result_likelihood, p.draw_result_likelihood, p.away_result_likelihood,
             p.over_0_5_likelihood, p.over_1_5_likelihood, p.over_2_5_likelihood, p.fixtures_used
      FROM head_to_head_predictions p
      JOIN live_fixtures l ON l.id=p.fixture_id
      WHERE p.matches_used >= 3
      ORDER BY l.country, l.competition, l.home_team
    """).fetchall()
    all_matches = []
    for country, competition, season, date, home, away, hg, ag in con.execute("SELECT country,competition,season,match_date,home_team,away_team,full_time_home_goals,full_time_away_goals FROM matches WHERE full_time_home_goals IS NOT NULL AND full_time_away_goals IS NOT NULL"):
        all_matches.append((country, competition, canonical_season(season), date, home, away, hg, ag))
    cards = []
    for country, league, home, away, sample, home_win, draw, away_win, o05, o15, o25, saved_fixtures in rows:
        used = [f"<li><b>{html.escape(season)}</b> · {html.escape(home)} {hg}–{ag} {html.escape(away)}</li>" for season, _, _, hg, ag in json.loads(saved_fixtures)]
        home_pct, draw_pct, away_pct = result_percentages([home_win, draw, away_win])
        pair = [row for row in all_matches if norm(row[0]) == norm(country) and norm(home) in (norm(row[4]), norm(row[5])) and norm(away) in (norm(row[4]), norm(row[5]))]
        if pair:
            newest = max(season_rank(row[2]) for row in pair)
            latest = [row for row in pair if season_rank(row[2]) == newest]
            season, competition = latest[0][2], latest[0][1]
            league_matches = [row for row in all_matches if norm(row[0]) == norm(country) and norm(row[1]) == norm(competition) and row[2] == season]
            home_games = [row for row in league_matches if norm(row[4]) == norm(home)]
            away_games = [row for row in league_matches if norm(row[5]) == norm(away)]
            home_form, home_for, home_against = form(home_games, home, True)
            away_form, away_for, away_against = form(away_games, away, False)
            points = {}
            for _, _, _, _, h, a, hg, ag in league_matches:
                points.setdefault(h, 0); points.setdefault(a, 0)
                if hg > ag: points[h] += 3
                elif ag > hg: points[a] += 3
                else: points[h] += 1; points[a] += 1
            ordered = sorted(points, key=lambda team: (-points[team], team))
            positions = {team: index + 1 for index, team in enumerate(ordered)}
            context = f'''<section class="context"><div><span><b>Home form</b>{home_form}<em>{home_for} scored · {home_against} conceded</em></span><span><b>Away form</b>{away_form}<em>{away_for} scored · {away_against} conceded</em></span></div><p>Table position: {html.escape(home)} #{positions.get(home, '—')} · {html.escape(away)} #{positions.get(away, '—')}</p></section>'''
        else:
            context = '<section class="context"><small>Current-season context</small><p>No completed current-season data is available for both teams yet.</p></section>'
        cards.append(f'''<article class="card">
          <p class="eyebrow">{html.escape(country)} · {html.escape(league)}</p>
          <h2>{html.escape(home)} <span>vs</span> {html.escape(away)}</h2>
          <div class="result"><small>Likely result</small><div><b>{html.escape(home)}</b><strong>{home_pct}</strong></div><div><b>Draw</b><strong>{draw_pct}</strong></div><div><b>{html.escape(away)}</b><strong>{away_pct}</strong></div></div>
          <div class="goals"><div><small>Over 0.5</small><b>{pct(o05)}</b></div><div><small>Over 1.5</small><b>{pct(o15)}</b></div><div><small>Over 2.5</small><b>{pct(o25)}</b></div></div>
          <p class="sample">{sample} recent direct home-versus-away fixtures, within three seasons</p><ul class="history">{''.join(used)}</ul>
          {context}
        </article>''')
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Match Signal</title><style>
      *{{box-sizing:border-box}}body{{margin:0;background:#08131f;color:#eef5fa;font:16px/1.45 Arial,sans-serif}}main{{max-width:1200px;margin:auto;padding:56px 24px 80px}}.top{{display:flex;justify-content:space-between;gap:24px;align-items:end;border-bottom:1px solid #294152;padding-bottom:30px;margin-bottom:30px}}h1{{font-size:clamp(2.3rem,6vw,5rem);line-height:.95;margin:0;letter-spacing:-.07em}}.intro{{color:#9fb4c3;max-width:460px;margin:14px 0 0}}.badge{{background:#b8ff4e;color:#102000;border-radius:99px;padding:8px 12px;font-weight:bold;white-space:nowrap}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px;align-items:stretch}}.card{{background:#102536;border:1px solid #294557;border-radius:18px;padding:22px;box-shadow:0 12px 28px #0003;display:flex;flex-direction:column}}.eyebrow,small{{text-transform:uppercase;letter-spacing:.08em;font-size:.72rem;color:#93aabb}}h2{{font-size:1.22rem;line-height:1.2;min-height:2.4em;margin:7px 0 24px}}h2 span{{font-weight:normal;color:#738b9c;font-size:.9rem}}.result{{background:#16364a;border-radius:12px;padding:15px;display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.result small{{grid-column:1/-1}}.result div{{border-left:1px solid #416177;padding-left:9px}}.result div:first-of-type{{border:0;padding-left:0}}.result b{{font-size:.76rem;display:block;color:#c6d7e0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.result strong{{display:block;font-size:1.25rem;color:#b8ff4e}}.goals{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}}.goals div{{background:#0c1d2b;padding:10px;border-radius:10px}}.goals b{{display:block;font-size:1.15rem;color:#d6e8f2}}.sample{{color:#7992a3;font-size:.8rem;margin:0 0 7px}}.history{{border-top:1px solid #294557;margin:12px 0 0;padding:10px 0 0;min-height:142px;list-style:none;color:#b8c8d3;font-size:.8rem}}.history li{{padding:3px 0}}.history b{{color:#b8ff4e}}.context{{margin-top:auto;padding:13px;background:#0c1d2b;border-radius:12px;color:#c7d7e0;font-size:.8rem}}.context div{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.context span{{line-height:1.7}}.context span b,.context em{{display:block;font-style:normal;color:#8fa7b7;font-size:.72rem}}.context p{{margin:10px 0 0;color:#9eb2c0}}footer{{color:#7992a3;margin-top:36px;font-size:.85rem}}@media(max-width:600px){{main{{padding-top:34px}}.top{{display:block}}.badge{{display:inline-block;margin-top:20px}}}}
    </style></head><body><main><section class="top"><div><h1>Match Signal</h1><p class="intro">Direct home-versus-away signals from the newest three available seasons.</p></div><span class="badge">{len(rows)} live predictions</span></section><section class="grid">{''.join(cards)}</section><footer>Winner and over-goals likelihoods are descriptive historical rates, not guarantees.</footer></main></body></html>'''
    OUT.write_text(document, encoding="utf-8")
    print(f"Rendered {len(rows)} prediction cards")

if __name__ == "__main__":
    main()
