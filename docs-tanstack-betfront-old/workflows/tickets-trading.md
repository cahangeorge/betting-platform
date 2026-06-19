# Workflow: Tickets and Trading

## Tickets page workflow

`/tickets` had two top-level tabs:

1. `Generate Tickets`
2. `Flumine`

## Generate Tickets tab

`TicketsPanel` itself had three subtabs:

- `✋ Manual Build`
- `🔮 Prediction Build`
- `📋 Saved Tickets`

## Manual Build

### Visual blocks

- Match browser with search field.
- Selection dialog for choosing a market/outcome from a match.
- Ticket builder card.
- Computed stats panel.

### Functionality

- Search teams or league.
- Browse matches and available odds.
- Add a selected market/outcome to a ticket.
- Update an existing selection.
- Remove selections.
- Set ticket name and stake.
- Save ticket to SQLite.

## Prediction Build

### Visual blocks

- Prediction browser.
- Value bet candidates.
- Add all value bets button.
- Same ticket builder stats as manual build.

### Functionality

- Convert prediction rows into ticket selections.
- Use probabilities and bookmaker odds to identify value bets.
- Add all candidate value bets to a ticket.
- Compute combined ticket metrics.

## Saved Tickets

### Functionality

- List saved tickets.
- Show stake, combined odds, combined probability, EV, potential return.
- Delete saved tickets.

## Ticket statistics

The old server logic computed:

- Combined decimal odds.
- Combined probability.
- Expected value.
- Potential return.
- Ticket type label based on number of selections.

## Market/outcome mapping

The implementation handled labels for:

- 1X2 outcomes.
- Totals.
- BTTS.
- Draw-no-bet.
- Double chance.
- Asian handicap-style values.

## Flumine tab

This was a placeholder/concept for Betfair Exchange trading.

### Controls

- Market:
  - Match Odds
  - Over/Under 2.5 Goals
  - Both Teams To Score
  - Correct Score
  - Asian Handicap
- Strategy Type:
  - Back
  - Lay
  - Back & Lay in-play trading
- Execution Mode:
  - Simulated paper trading
  - Live Betfair Exchange
- Max Bet Size.
- Max Loss Limit.

### Behavior

- Bridge integration was explicitly marked in progress.
- Start Strategy button was disabled.
- How-it-works block explained the intended flow:
  1. Connect Betfair credentials.
  2. Select market and strategy.
  3. Set risk controls.
  4. Validate in simulated mode.
  5. Switch to live mode.

## Migration notes for Svelte platform

- Preserve ticket creation from both manual odds and predictions.
- Store selections in a typed backend schema, not only JSON blobs.
- Keep EV and probability calculations server-side for auditability.
- Keep Flumine as future/optional until backend bridge and credentials are production-safe.
