# Paired Fast/Reason routing replay

Development replay of historical multi-call strategies; local Coding tests are not official hidden correctness, this is not a live bounded-policy result, and the replay does not estimate the new endgame verification phase.

## Paired development evidence

| Category | Tasks | Reason reward/cost | Fast reward/cost | R-only wins | F-only wins |
|---|---:|---:|---:|---:|---:|
| math | 80 | 272/51722.2 | 224/37786.6 | 11 | 4 |
| search | 32 | 114/6659.8 | 110/1275.0 | 1 | 1 |
| data_analysis | 80 | 248/67467.2 | 329/41900.3 | 0 | 15 |
| coding | 80 | 184/47234.5 | 167/40567.3 | 5 | 3 |

## Balanced 100-task bootstrap replay

| Policy | Mean reward | 5–95% | Δ vs Fast | Δ 5–95% | P(win)/P(loss) | Mean spent |
|---|---:|---:|---:|---:|---:|---:|
| all_fast | 311.43 | 273–353 | +0.00 | +0–+0 | 0.0%/0.0% | 38576.7 |
| all_reason | 309.86 | 269–351 | -1.57 | -31–+28 | 44.2%/53.8% | 57303.7 |
| math_reason | 326.51 | 285–368 | +15.09 | -5–+36 | 88.4%/9.8% | 42991.8 |
| math_coding_reason | 331.92 | 291–375 | +20.49 | -3–+45 | 91.1%/7.5% | 45112.7 |

The implemented `empirical_hybrid` corresponds to `math_coding_reason`.
It keeps evaluation labels outside the runtime strategy.

## Interpretation and limits

- Use Reason for Math: it has 11 exclusive wins against 4 for Fast.
- Use Fast for Search: correctness is tied while historical cost is much lower.
- Use Fast for Data Analysis: it has 15 exclusive wins and Reason has none.
- Coding is the weakest routing conclusion (5 versus 3 exclusive wins).
- Do not fit task-ID or answer-derived routing rules; that would leak benchmark construction.
- Keep the online text-quality head frozen until independent correctness labels exist.
  Runtime text answers are unverified, so their success labels are not learnable online.
- The cost head may continue learning from settled provider usage only.
- Endgame verification is not included in these replay scores; measure its correction
  and regression rates separately before attributing any additional reward to it.
- Validate this candidate with a fresh live paired run, then open the final holdout once.
