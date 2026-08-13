# MatchSignal 2.0 model

MatchSignal estimates the expected goals for each team before kickoff, then
converts those estimates into market probabilities with a Poisson score model.

## Version 2.1.0

1. Historical matches are imported into a normalised database.
2. Features are calculated only from matches before the fixture kickoff.
3. Home and away form are separate. Recent matches receive more weight.
4. An Elo rating is updated chronologically, never retrospectively.
5. Expected goals combine the league baseline, attack/defence ratios, recent
   home/away scoring rates, and a small Elo adjustment.
6. Independent Poisson distributions generate score probabilities from 0–8
   goals. Result, goals, BTTS, team-goals and double-chance probabilities are
   derived from that matrix.

Predicted probability describes the model estimate. Confidence is separately
based on usable sample size and statistic completeness.

## Limitations

This is a team-level model, not shot-level expected goals. Shots, shots on
target, corners, fouls and cards use separate count models: recent home/away
team rates, opponent rates conceded and a league baseline produce an expected
count, then a Poisson distribution produces the over-market probabilities.
Each market is withheld unless it has 20 usable league rows and five usable
home/away rows for both teams. “Cards” means yellow cards plus red cards in the
underlying Football-Data rows. No prediction is a guarantee.
