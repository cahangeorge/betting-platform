# Pre-Match Betting Case Studies

> Reference material for pre-match football betting strategies. Each case study documents
> the mathematical basis, entry rules, expected edge, and relevant academic literature.

---

## Case Study 1: Poisson Goals Model

### Strategy Name
**Poisson Regression for Match Outcome Prediction**

### Core Concept
Model the number of goals scored by each team in a match as independent Poisson random variables. Estimate each team's expected goals (λ) using historical data, attacking/defensive strengths, and contextual factors. From the joint goal distribution, compute the probability of each outcome (home win, draw, away win) and compare to bookmaker odds to find value.

### Mathematical / Statistical Basis

**Poisson Probability Mass Function:**
```
P(X = k) = (λ^k × e^(-λ)) / k!
```

**Expected Goals for Each Team:**
```
λ_home = α_home × β_away × γ_league
λ_away = α_away × β_home × γ_league
```

Where:
- `α_i` = attacking strength of team i
- `β_j` = defensive strength of team j (conceded goals rate)
- `γ_league` = league average goal rate (normalization factor)

**Match Outcome Probabilities (from joint Poisson):**
```
P(Home Win) = Σ_{i>j} P(Home=i) × P(Away=j)
P(Draw) = Σ_{k} P(Home=k) × P(Away=k)
P(Away Win) = Σ_{j>i} P(Home=i) × P(Away=j)
```

**Calibration via Maximum Likelihood:**
```
L(α, β) = ∏_{matches} P(home_goals | λ_home) × P(away_goals | λ_away)
```

### Entry Rules

1. **Model probability ≥ implied probability + 15% edge** (e.g., model says 40% win, odds imply 25%)
2. **Minimum 10 matches of historical data** per team in current season
3. **No entry if both teams' form is unknown** (e.g., promoted team with no top-flight data)
4. **Odds ≥ 2.0** — need sufficient payout for the entry-only model
5. **Kelly criterion stake**: `f* = (p × b - q) / b` where `b = odds - 1`
6. **Pre-match only**: bet placed ≥ 1 hour before kickoff to avoid late team news impact on odds

### Expected Edge

| Metric | Value |
|--------|-------|
| Accuracy (1X2) | 50–55% |
| Expected ROI per bet | 5–12% |
| Kelly fraction | 5–10% of edge / (odds-1) |
| Volume | ~5–15 qualifying bets per match day |
| Draw prediction accuracy | 45–50% |

### Implementation Notes

- **Data source**: football-data.co.uk (14+ seasons of historical odds and results)
- Season-level calibration: retrain parameters at the start of each season
- League-specific: each league has different baseline goal rates (Bundesliga ~3.1 goals/game, Ligue 1 ~2.6)
- The independence assumption between home/away goals is the main limitation — Dixon-Coles (Case Study 2) addresses this
- **Entry-only model**: once bet is placed, ride to final whistle. No cash-out, no exit
- Staking: fractional Kelly (0.25-0.5x) due to model uncertainty
- This model works best for **goals markets** (Over/Under, Both Teams to Score) where the Poisson structure is most natural

### Academic References

1. **Maher, M.J. (1982).** *Modelling soccer matches.* Journal of the Royal Statistical Society, Series A, 145(4), 427–441.
   - The foundational paper for Poisson-based soccer prediction. Introduced the attack/defense strength decomposition.

2. **Dixon, M.J. & Coles, S.G. (1997).** *Modelling Association Football Scores and Inefficiencies in the Football Betting Market.* Journal of the Royal Statistical Society: Series C, 46(2), 265–280.
   - Extended the Poisson model with a correlation parameter for low-scoring draws. The standard reference for Poisson football models.

3. **arXiv:2403.16282 (2024).** *The Evolution of Football Betting: A Machine Learning Approach to Match Outcome Forecasting and Bookmaker Odds Estimation.* [https://arxiv.org/abs/2403.16282](https://arxiv.org/abs/2403.16282)
   - Compares Poisson-based approaches with ML models (XGBoost, Random Forest). XGBoost achieves 65-70% accuracy but Poisson models remain interpretable and competitive.

4. **arXiv:2410.21484 (2024).** *A Systematic Review of Machine Learning in Sports Betting: Techniques, Challenges, and Future Directions.* [https://arxiv.org/abs/2410.21484](https://arxiv.org/abs/2410.21484)
   - Comprehensive review noting that Stenerud (2015) achieved small profit over 5 seasons using a Poisson process model on football-data.co.uk.

---

## Case Study 2: Dixon-Coles with Home Advantage

### Strategy Name
**Dixon-Coles Correlated Poisson Model with Home Advantage Decomposition**

### Core Concept
An extension of the basic Poisson model that (1) introduces a correlation parameter ρ to account for the dependency between home and away goal-scoring in low-scoring matches, and (2) decomposes home advantage into separate attacking and defensive components rather than a single multiplicative factor. This addresses the well-known limitation that standard Poisson models underpredict 0-0, 1-0, 0-1, and 1-1 draws.

### Mathematical / Statistical Basis

**Standard Poisson (Maher):**
```
P(X=i, Y=j) = P(X=i) × P(Y=j)    [independent]
```

**Dixon-Coles Correction:**
```
P(X=i, Y=j) = τ(i, j, λ, μ, ρ) × P(X=i) × P(Y=j)
```

Where τ is the correction factor:
```
τ(i, j, λ, μ, ρ) =
  1 - λμρ           if i=0, j=0
  1 + ρ             if i=0, j=1
  1 + ρ             if i=1, j=0
  1 - ρ             if i=1, j=1
  1                 otherwise
```

**Home Advantage Decomposition:**
```
λ_home = exp(α_home - β_away + γ_home)
μ_away = exp(α_away - β_home + γ_away)
```

Where:
- `γ_home` = home advantage for attacking (typically +0.2 to +0.3)
- `γ_away` = away advantage for defending (typically -0.1 to 0)
- `α_i` = attack strength (log-scale)
- `β_i` = defense strength (log-scale)

**Time Decay:**
```
weight(match) = exp(-δ × days_since_match)
```
Recent matches are weighted more heavily. Typical `δ = 0.0019` (half-life ≈ 365 days).

### Entry Rules

1. **Model probability ≥ implied probability + 15% edge**
2. **Minimum 20 matches** of historical data per team
3. **Home advantage factor γ_home > 0** — validate it exists in the data
4. **Correlation parameter ρ < 0** — should be negative (low-scoring draws correlated)
5. **No entry if ρ confidence interval includes 0** — model may be misspecified
6. **Odds ≥ 2.0** for the backed selection
7. **Kelly stake at 0.25-0.5x** due to model uncertainty

### Expected Edge

| Metric | Value |
|--------|-------|
| Accuracy (1X2) | 52–57% |
| Expected ROI per bet | 6–14% |
| Draw accuracy improvement | +3–5% over standard Poisson |
| Volume | ~4–12 qualifying bets per match day |
| Brier score | 0.20–0.22 |

### Implementation Notes

- **ρ typically ≈ -0.13** (negative correlation between home/away goals in low-scoring games)
- Home advantage varies by league: EPL ~0.35, La Liga ~0.30, Bundesliga ~0.25, Serie A ~0.30
- **Re-estimate parameters weekly** — use maximum likelihood with the exponential time decay
- The Dixon-Coles model is the standard starting point for any football prediction model
- For implementation, use scipy.optimize.minimize with Nelder-Mead to fit parameters
- **Entry-only model**: bet placed pre-match, ride to final whistle
- The correction factor ρ has the biggest impact on draw predictions — this is where the edge is largest

### Academic References

1. **Dixon, M.J. & Coles, S.G. (1997).** *Modelling Association Football Scores and Inefficiencies in the Football Betting Market.* Journal of the Royal Statistical Society: Series C, 46(2), 265–280.
   - The foundational paper. Introduces the τ correction factor and time-decay weighting. Shows the model captures draw probabilities better than standard Poisson.

2. **Koopman, S.J. & Lit, R. (2015).** *A dynamic bivariate Poisson model for analysing and forecasting match results in the English Premier League.* Journal of the Royal Statistical Society: Series A, 178(1), 167–186.
   - Extends Dixon-Coles with time-varying parameters and dynamic home advantage.

3. **arXiv:2605.16066 (2026).** *A market-calibrated accelerated failure time model for in-play football forecasting.* [https://arxiv.org/abs/2605.16066](https://arxiv.org/abs/2605.16066)
   - References Dixon-Coles as the foundational pre-match model. Notes that pre-match Poisson models have a long history but in-play models struggle to match market accuracy.

4. **arXiv:1811.03931 (2018).** *Risk-Neutral Pricing and Hedging of In-Play Football Bets.* [https://arxiv.org/abs/1811.03931](https://arxiv.org/abs/1811.03931)
   - Uses Poisson processes with constant intensities as the baseline model for in-play pricing, building on the Dixon-Coles framework.

---

## Case Study 3: Elo Rating Adjustments

### Strategy Name
**Elo-Based Match Prediction with Home Advantage and Goal Margin Adjustments**

### Core Concept
Use the Elo rating system — originally designed for chess — adapted for football to estimate the relative strength of two teams. The key insight is that Elo ratings are self-correcting and adapt to team quality changes over time. By calibrating Elo parameters specifically for football (including home advantage, goal margin multipliers, and season carry-over), we get a robust estimate of match outcome probabilities.

### Mathematical / Statistical Basis

**Elo Update Rule:**
```
R_new = R_old + K × (S - E)
```

Where:
- `R_old` = current rating before the match
- `K` = update factor (typically 20 for football, higher for more recent matches)
- `S` = actual outcome (1 = win, 0.5 = draw, 0 = loss)
- `E` = expected outcome: `E = 1 / (1 + 10^((R_opp - R_self + H) / 400))`
- `H` = home advantage parameter (typically 65-100 Elo points)

**Goal Margin Multiplier:**
```
G = ln(|margin| + 1) × (2.2 / (E_diff × 0.001 + 2.2))
```
Where `margin` is goal difference and `E_diff` is the expected score difference. This prevents large-margin wins from having disproportionate impact when a blowout was expected.

**Win Probability from Elo:**
```
P(A wins) = E_A = 1 / (1 + 10^((R_B - R_A + H) / 400))
P(B wins) = E_B = 1 / (1 + 10^((R_A - R_B - H) / 400))
P(Draw) = 1 - P(A wins) - P(B wins) [calibrated from historical draw rates]
```

**Season Carry-Over:**
```
R_start_season = R_end_season × 0.75 + 1500 × 0.25
```
Regression toward the mean (1500) between seasons — 75% carry-over is standard.

### Entry Rules

1. **Model probability ≥ implied probability + 15% edge**
2. **Minimum 30 Elo-rated matches** per team (avoid teams with insufficient history)
3. **Elo difference < 400** — avoid extreme mismatches where market is efficient
4. **Home advantage calibrated per league** — use league-specific H value
5. **Odds ≥ 2.0** for the backed selection
6. **No entry on promoted/relegated teams** until they have 10+ matches in new league
7. **Kelly stake at 0.25-0.5x**

### Expected Edge

| Metric | Value |
|--------|-------|
| Accuracy (1X2) | 50–55% |
| Expected ROI per bet | 4–10% |
| Draw calibration | Poor (Elo doesn't model draws well natively) |
| Volume | ~3–8 qualifying bets per match day |
| Correlation with market odds | 0.85–0.90 |

### Implementation Notes

- **Initial ratings**: assign based on historical league finish (champion = 1800, relegated = 1200, etc.)
- Home advantage varies: EPL H=65, La Liga H=75, Bundesliga H=80
- **Elo alone is insufficient** — use as a feature in the ensemble (Case Study 5)
- The main weakness is draw prediction — Elo is designed for win/loss, not draws
- **Update after every match** using the standard formula
- Use the Glicko-2 system for rating uncertainty if you want confidence intervals
- **Entry-only model**: pre-match bet, ride to final whistle

### Academic References

1. **Elo, A.E. (1978).** *The Rating of Chessplayers, Past and Present.* Arco Publishing.
   - The foundational Elo system. Adapted for football by many researchers.

2. **arXiv:2505.01902 (2025).** *From Players to Champions: A Generalizable Machine Learning Approach for Match Outcome Prediction with Insights from the FIFA World Cup.* [https://arxiv.org/abs/2505.01902](https://arxiv.org/abs/2505.01902)
   - Uses team-level statistics including Elo-derived strength metrics as features. Demonstrates that relative team strength is a crucial predictive feature.

3. **arXiv:2409.13098 (2024).** *Predicting soccer matches with complex networks and machine learning.* [https://arxiv.org/abs/2409.13098](https://arxiv.org/abs/2409.13098)
   - Combines complex network metrics with match statistics for prediction. Uses relative team strength as a key feature alongside network-based metrics.

4. **arXiv:2410.09068 (2024).** *Modeling and Prediction of the UEFA EURO 2024 via Combined Statistical Learning Approaches.* [https://arxiv.org/abs/2410.09068](https://arxiv.org/abs/2410.09068)
   - Uses combined statistical models incorporating team strength ratings for tournament prediction. Demonstrates that France (19.2%) was the pre-tournament favorite.

---

## Case Study 4: Team Form Regression

### Strategy Name
**Rolling Form Regression with Contextual Adjustment**

### Core Concept
Quantify a team's current form using a regression model that captures recent performance trends (last 5-10 matches) weighted by recency, opponent strength, and match context (home/away, cup vs league). The form score is then used as a feature to predict match outcomes, with the key insight that form is *mean-reverting* — teams performing significantly above/below their baseline will revert.

### Mathematical / Statistical Basis

**Form Score Calculation:**
```
Form(t) = Σ_{i=1}^{n} w_i × Performance(match_i)
```

Where:
```
w_i = exp(-δ × (t - t_i))    [exponential time decay]
Performance(match_i) = {
  3 for win, 1 for draw, 0 for loss,
  + bonus for clean sheets, + bonus for goals scored,
  - penalty for goals conceded
}
```

**Regression Model:**
```
P(outcome) = σ(β₀ + β₁×Form_home + β₂×Form_away + β₃×Home + β₄×Elo_diff + β₅×xG_form)
```

Where σ is the logistic function.

**Mean Reversion Adjustment:**
```
Form_adjusted(t) = Form(t) + γ × (Baseline - Form(t))
```

Where `γ` is the reversion strength (typically 0.1-0.3) and `Baseline` is the team's historical average form.

**Opponent-Strength-Adjusted Form:**
```
Adj_Form(t) = Σ_{i=1}^{n} w_i × Performance(match_i) / opponent_Elo(match_i)
```

### Entry Rules

1. **Model probability ≥ implied probability + 15% edge**
2. **Form divergence > 2 standard deviations** from team's baseline (extreme form = reversion opportunity)
3. **Minimum 5 matches** of form data in current season
4. **Adjust for opponent strength** — beating weak teams counts less
5. **Odds ≥ 2.0** for the backed selection
6. **No entry in first 3 matchdays** of season — insufficient form data
7. **Kelly stake at 0.25-0.5x**

### Expected Edge

| Metric | Value |
|--------|-------|
| Accuracy (1X2) | 51–56% |
| Expected ROI per bet | 5–11% |
| Form reversion accuracy | 55–60% (when form is extreme) |
| Volume | ~3–10 qualifying bets per match day |
| Best for | Mid-table teams with consistent form |

### Implementation Notes

- **Form is the most overbet feature** — the public loves backing "in-form" teams, creating value on fading extreme form
- The reversion signal is strongest when:
  - A team has won 5+ in a row (expect regression)
  - A team has lost 4+ in a row (expect recovery)
  - But only if underlying metrics (xG, shots) don't support the streak
- **Combine with xG form**: xG-based form is more predictive than results-based form
- Weighting: last 5 matches = 60% of form, previous 5 = 30%, season average = 10%
- **Entry-only model**: pre-match bet, ride to final whistle
- This strategy works best in leagues with high competitive balance (Eredivisie, Championship)

### Academic References

1. **arXiv:2403.16282 (2024).** *The Evolution of Football Betting: A Machine Learning Approach to Match Outcome Forecasting and Bookmaker Odds Estimation.* [https://arxiv.org/abs/2403.16282](https://arxiv.org/abs/2403.16282)
   - Identifies recent form as a key predictive feature. XGBoost models incorporating form data achieve 65-70% accuracy.

2. **arXiv:2505.01902 (2025).** *From Players to Champions: A Generalizable Machine Learning Approach for Match Outcome Prediction.* [https://arxiv.org/abs/2505.01902](https://arxiv.org/abs/2505.01902)
   - Uses team-level statistics including recent results as features. Demonstrates that form-based features are crucial for generalizable prediction.

3. **arXiv:2410.21484 (2024).** *A Systematic Review of Machine Learning in Sports Betting.* [https://arxiv.org/abs/2410.21484](https://arxiv.org/abs/2410.21484)
   - Notes that relative team strength and player form are identified as crucial predictive features across multiple studies.

4. **arXiv:2602.16830 (2026).** *The Impact of Formations on Football Matches Using Double Machine Learning.* [https://arxiv.org/abs/2602.16830](https://arxiv.org/abs/2602.16830)
   - Uses XGBoost regressor to predict goal difference from confounding variables. Demonstrates how contextual factors (formations, recent changes) affect match outcomes.

---

## Case Study 5: Bayesian Ensemble

### Strategy Name
**Bayesian Model Averaging Ensemble for Robust Probability Estimation**

### Core Concept
Combine multiple prediction models (Poisson, Dixon-Coles, Elo, form regression, xG-based) using Bayesian Model Averaging (BMA). Each model's prediction is weighted by its posterior probability of being the best model, which is computed from its historical performance. The ensemble produces more robust probability estimates than any single model and naturally handles model uncertainty.

### Mathematical / Statistical Basis

**Bayesian Model Averaging:**
```
P(outcome | data) = Σ_{m=1}^{M} P(outcome | model_m, data) × P(model_m | data)
```

**Posterior Model Probability:**
```
P(model_m | data) ∝ P(data | model_m) × P(model_m)
```

Where:
```
P(data | model_m) = ∏_{matches} P(outcome_i | model_m, θ_m)
```

**Leave-One-Out Cross-Validation Weights:**
```
w_m = exp(-CV_score_m) / Σ_{j} exp(-CV_score_j)
```

Where `CV_score_m` is the log-likelihood of model `m` on held-out data.

**Component Models:**

| Model | Weight (typical) | Strength |
|-------|-----------------|----------|
| Poisson | 0.15 | Goals market prediction |
| Dixon-Coles | 0.25 | Draw prediction, low-scoring |
| Elo | 0.15 | Long-term team strength |
| Form Regression | 0.10 | Recent trends |
| xG-Based | 0.20 | Shot quality analysis |
| ML (XGBoost) | 0.15 | Non-linear interactions |

**Ensemble Probability:**
```
P_final(outcome) = Σ_m w_m × P_m(outcome)
```

**Uncertainty Quantification:**
```
Var(P_final) = Σ_m w_m × (P_m - P_final)²
```

If `Var(P_final)` is high, the models disagree — reduce stake or skip the bet.

### Entry Rules

1. **Ensemble probability ≥ implied probability + 15% edge**
2. **Model agreement > 0.7** — at least 70% of models agree on the direction
3. **Variance of ensemble predictions < 0.05** — models must not disagree too much
4. **Minimum 3 component models** must have sufficient data to make predictions
5. **Odds ≥ 2.0** for the backed selection
6. **No entry if ensemble variance > 0.10** — too much disagreement, skip
7. **Kelly stake at 0.25-0.5x** — further reduced due to ensemble uncertainty

### Expected Edge

| Metric | Value |
|--------|-------|
| Accuracy (1X2) | 54–60% |
| Expected ROI per bet | 8–16% |
| Draw accuracy | 48–54% |
| Volume | ~3–10 qualifying bets per match day |
| Brier score | 0.19–0.21 |
| Model agreement rate | 75–85% |

### Implementation Notes

- **Ensemble is the recommended production model** — it's more robust than any single model
- Update model weights weekly using the last 100 matches of predictions
- **Key advantage**: if one model is wrong, the others compensate
- **Key disadvantage**: harder to debug and interpret than single models
- Use `scikit-learn` for the XGBoost component, `scipy` for Poisson/Dixon-Coles, custom Elo implementation
- Store all component predictions in the database for post-match analysis
- **Entry-only model**: pre-match bet, ride to final whistle
- The 15% edge threshold is applied to the *ensemble* probability, not individual models

### Academic References

1. **arXiv:2403.16282 (2024).** *The Evolution of Football Betting: A Machine Learning Approach to Match Outcome Forecasting and Bookmaker Odds Estimation.* [https://arxiv.org/abs/2403.16282](https://arxiv.org/abs/2403.16282)
   - Compares multiple ML models and demonstrates that ensemble approaches (combining XGBoost with other methods) improve prediction accuracy over individual models.

2. **arXiv:2505.01902 (2025).** *From Players to Champions: A Generalizable Machine Learning Approach for Match Outcome Prediction.* [https://arxiv.org/abs/2505.01902](https://arxiv.org/abs/2505.01902)
   - Uses majority voting mechanism to aggregate predictions from multiple models. Demonstrates that ensemble aggregation outperforms individual model predictions.

3. **arXiv:2410.09068 (2024).** *Modeling and Prediction of the UEFA EURO 2024 via Combined Statistical Learning Approaches.* [https://arxiv.org/abs/2410.09068](https://arxiv.org/abs/2410.09068)
   - Combines multiple statistical models for tournament prediction. Uses combined model to identify tournament favorites with calibrated probabilities.

4. **arXiv:2410.21484 (2024).** *A Systematic Review of Machine Learning in Sports Betting.* [https://arxiv.org/abs/2410.21484](https://arxiv.org/abs/2410.21484)
   - Comprehensive review noting that hybrid models combining multiple approaches consistently outperform individual models across studies.

5. **arXiv:2311.13707 (2023).** *Bayes-xG: Player and Position Correction on Expected Goals (xG) using Bayesian Hierarchical Approach.* [https://arxiv.org/abs/2311.13707](https://arxiv.org/abs/2311.13707)
   - Demonstrates Bayesian hierarchical modeling for football metrics. The Bayesian framework naturally handles uncertainty and model averaging.

---

## Strategy Comparison Summary

| Feature | Poisson | Dixon-Coles | Elo | Form Regression | Bayesian Ensemble |
|---------|---------|-------------|-----|-----------------|-------------------|
| **Accuracy** | 50–55% | 52–57% | 50–55% | 51–56% | 54–60% |
| **Expected ROI** | 5–12% | 6–14% | 4–10% | 5–11% | 8–16% |
| **Draw accuracy** | Poor | Good | Poor | Moderate | Good |
| **Data required** | Moderate | Moderate | Low | Moderate | High |
| **Complexity** | Low | Medium | Low | Medium | High |
| **Interpretability** | High | High | High | Medium | Low |
| **Volume** | 5–15/day | 4–12/day | 3–8/day | 3–10/day | 3–10/day |

### Recommended Portfolio Allocation

For a combined pre-match betting portfolio:
- **35% allocation** to Bayesian Ensemble (highest accuracy, most robust)
- **25% allocation** to Dixon-Coles (strong draw prediction, interpretable)
- **15% allocation** to Poisson (goals market specialist)
- **15% allocation** to Form Regression (captures recent trends)
- **10% allocation** to Elo (long-term strength baseline)

All strategies use **entry-only trades** (no exits) and **Kelly criterion staking** (fractional Kelly at 0.25-0.5x for risk management).

---

## Cross-Strategy Notes

### Entry-Only Model (All Strategies)
All pre-match strategies share the same execution model:
1. Calculate model probability
2. Compare to market odds
3. If edge > 15%, place bet
4. Ride to final whistle — **no exits, no cash-outs, no stop-losses**
5. Use fractional Kelly (0.25-0.5x) for position sizing

### Why Entry-Only Works
- Eliminates behavioral biases in exit decisions
- Forces the model to be accurate — no "hope" to fall back on
- Matches the profile of a successful Reddit bot (1200% ROI, 50% WR, 3.0 avg odds)
- Simplifies execution — one decision point per match

### Data Pipeline
```
football-data.co.uk → Historical odds + results
StatsBomb/FBRef → xG data
Sofascore API → Live event feeds
Betfair/Matchbook → Live odds
→ Model computation → Edge detection → Kelly sizing → Bet placement
```

---

*Last updated: 2026-06-03*
*Document version: 1.0*
