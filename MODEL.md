# MatchSignal 2.0 model

MatchSignal estimates the expected goals for each team before kickoff, then
converts those estimates into market probabilities with a Poisson score model.

## Version 2.0.0 foundation

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

This is a team-level model, not shot-level expected goals. Corners and cards
remain unavailable until the current league has sufficient source statistics.
No prediction is a guarantee.
