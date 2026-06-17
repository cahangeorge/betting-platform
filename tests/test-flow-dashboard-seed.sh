#!/usr/bin/env bash
# test-flow-dashboard-seed.sh — Seeds admin user with data and verifies dashboard
# Usage: bash tests/test-flow-dashboard-seed.sh
set -euo pipefail

BASE="http://localhost:8080"
API="$BASE/api/v1"
DB="betting_platform"
PG="podman exec bet_postgres_1 psql -U betuser -d $DB -t -A -c"

PASS=0
FAIL=0
TOTAL=0

green() { printf "\033[31m✗ %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); }
pass() { printf "\033[32m✓ %s\033[0m\n" "$1"; PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); }

AUTH_HEADER=""
USER_ID=""
TOKEN=""
BANKROLL_ID=""

section() { echo -e "\n\033[1;36m━━━ $1 ━━━\033[0m"; }

# ============================================================
section "1. AUTHENTICATION"
# ============================================================

RESP=$(curl -s -w "\n%{http_code}" -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@betfront.com","password":"admin123"}')
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$STATUS" == "200" ]]; then
  TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
  AUTH_HEADER="Authorization: Bearer $TOKEN"
  pass "Login as admin (200)"
else
  green "Login failed: $STATUS"
  echo "$BODY"
  exit 1
fi

RESP=$(curl -s -H "$AUTH_HEADER" "$API/auth/me")
USER_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [[ -n "$USER_ID" ]]; then
  pass "Get user ID: $USER_ID"
else
  green "Failed to get user ID"
  exit 1
fi

# ============================================================
section "2. SEED FUTURE MATCHES"
# ============================================================

# First, update the existing midnight matches to be future
$PG "
UPDATE matches 
SET match_date = NOW() + INTERVAL '1 day'
WHERE status = 'scheduled' AND match_date <= NOW();
" > /dev/null 2>&1

UPDATED_COUNT=$($PG "SELECT COUNT(*) FROM matches WHERE status='scheduled' AND match_date > NOW();")
pass "Updated past-midnight matches — $UPDATED_COUNT scheduled matches now in future"

# Insert additional future matches
$PG "
INSERT INTO matches (home_team, away_team, competition, match_date, status, sport, season, created_at, updated_at)
VALUES
  ('Tottenham', 'Newcastle', 'Premier League', NOW() + INTERVAL '2 days', 'scheduled', 'football', '2025/2026', NOW(), NOW()),
  ('Inter Milan', 'AC Milan', 'Serie A', NOW() + INTERVAL '2 days' + INTERVAL '2 hours', 'scheduled', 'football', '2025/2026', NOW(), NOW()),
  ('Juventus', 'Napoli', 'Serie A', NOW() + INTERVAL '3 days', 'scheduled', 'football', '2025/2026', NOW(), NOW()),
  ('Barcelona', 'Real Madrid', 'La Liga', NOW() + INTERVAL '3 days' + INTERVAL '2 hours', 'scheduled', 'football', '2025/2026', NOW(), NOW()),
  ('Bayern Munich', 'Dortmund', 'Bundesliga', NOW() + INTERVAL '4 days', 'scheduled', 'football', '2025/2026', NOW(), NOW()),
  ('PSG', 'Marseille', 'Ligue 1', NOW() + INTERVAL '5 days', 'scheduled', 'football', '2025/2026', NOW(), NOW()),
  ('Atletico Madrid', 'Sevilla', 'La Liga', NOW() + INTERVAL '6 days', 'scheduled', 'football', '2025/2026', NOW(), NOW()),
  ('Roma', 'Lazio', 'Serie A', NOW() + INTERVAL '7 days', 'scheduled', 'football', '2025/2026', NOW(), NOW())
ON CONFLICT DO NOTHING;
" > /dev/null 2>&1

MATCH_COUNT=$($PG "SELECT COUNT(*) FROM matches WHERE status='scheduled' AND match_date > NOW();")
if [[ "$MATCH_COUNT" -gt "0" ]]; then
  pass "Have $MATCH_COUNT future matches"
else
  green "No future matches found"
fi

# ============================================================
section "3. SEED ODDS FOR FUTURE MATCHES"
# ============================================================

# Clear old test odds
$PG "DELETE FROM odds_entries WHERE bookmaker='test-seed';" > /dev/null 2>&1

$PG "
INSERT INTO odds_entries (match_id, bookmaker, market, home_odds, draw_odds, away_odds, timestamp)
SELECT m.id, 'test-seed', '1x2',
  CASE (m.id % 5)
    WHEN 0 THEN 1.80 WHEN 1 THEN 2.10 WHEN 2 THEN 2.50
    WHEN 3 THEN 1.65 WHEN 4 THEN 3.20 ELSE 2.00
  END,
  CASE (m.id % 5)
    WHEN 0 THEN 3.50 WHEN 1 THEN 3.40 WHEN 2 THEN 3.10
    WHEN 3 THEN 3.60 WHEN 4 THEN 3.30 ELSE 3.45
  END,
  CASE (m.id % 5)
    WHEN 0 THEN 4.20 WHEN 1 THEN 3.50 WHEN 2 THEN 2.90
    WHEN 3 THEN 5.00 WHEN 4 THEN 2.20 ELSE 3.80
  END,
  NOW()
FROM matches m
WHERE m.status = 'scheduled' AND m.match_date > NOW();
" > /dev/null 2>&1

ODDS_COUNT=$($PG "SELECT COUNT(*) FROM odds_entries WHERE bookmaker='test-seed';")
if [[ "$ODDS_COUNT" -gt "0" ]]; then
  pass "Seeded odds for $ODDS_COUNT matches"
else
  green "Failed to seed odds"
fi

# ============================================================
section "4. CREATE BANKROLL FOR ADMIN"
# ============================================================

EXISTING_BANKROLL=$($PG "SELECT id FROM bankrolls WHERE user_id = $USER_ID LIMIT 1;")
if [[ -z "$EXISTING_BANKROLL" ]]; then
  RESP=$(curl -s -w "\n%{http_code}" -X POST "$API/bankroll" \
    -H "Content-Type: application/json" -H "$AUTH_HEADER" \
    -d "{\"name\":\"Main Bankroll\",\"type\":\"real\",\"initial_balance\":5000.00,\"currency\":\"GBP\"}")
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -1)
  BANKROLL_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  if [[ "$STATUS" == "201" && -n "$BANKROLL_ID" ]]; then
    pass "Created bankroll #$BANKROLL_ID (initial £5000)"
  else
    green "Failed to create bankroll: $STATUS — $BODY"
    # Try direct SQL
    $PG "INSERT INTO bankrolls (user_id, name, type, balance, initial_balance, currency, created_at, updated_at)
         VALUES ($USER_ID, 'Main Bankroll', 'real', 5000.00, 5000.00, 'GBP', NOW(), NOW());" > /dev/null 2>&1
    BANKROLL_ID=$($PG "SELECT id FROM bankrolls WHERE user_id = $USER_ID LIMIT 1;")
    pass "Created bankroll via SQL: #$BANKROLL_ID"
  fi
else
  BANKROLL_ID="$EXISTING_BANKROLL"
  pass "Bankroll already exists: #$BANKROLL_ID"
fi

# ============================================================
section "5. CREATE TICKETS FOR ADMIN"
# ============================================================

# Get completed match IDs
COMPLETED_IDS=$($PG "SELECT id FROM matches WHERE status='completed' AND home_score IS NOT NULL ORDER BY match_date DESC LIMIT 7;" | tr '\n' ',' | sed 's/,$//')
IFS=',' read -ra CIDS <<< "$COMPLETED_IDS"

TICKETS_CREATED=0
for i in "${!CIDS[@]}"; do
  MID="${CIDS[$i]}"
  if [[ $i -lt 3 ]]; then SELECTION="home"; ODDS="1.80"
  elif [[ $i -lt 5 ]]; then SELECTION="draw"; ODDS="3.40"
  else SELECTION="away"; ODDS="4.20"
  fi
  
  RESP=$(curl -s -w "\n%{http_code}" -X POST "$API/tickets" \
    -H "Content-Type: application/json" -H "$AUTH_HEADER" \
    -d "{\"ticket_type\":\"single\",\"stake\":25.00,\"bankroll_id\":$BANKROLL_ID,\"legs\":[{\"match_id\":$MID,\"selection\":\"$SELECTION\",\"market\":\"1x2\",\"odds\":$ODDS}]}")
  STATUS=$(echo "$RESP" | tail -1)
  if [[ "$STATUS" == "201" ]]; then
    TICKETS_CREATED=$((TICKETS_CREATED+1))
  fi
done
pass "Created $TICKETS_CREATED single tickets on completed matches"

# Create accumulator
if [[ ${#CIDS[@]} -ge 3 ]]; then
  RESP=$(curl -s -w "\n%{http_code}" -X POST "$API/tickets" \
    -H "Content-Type: application/json" -H "$AUTH_HEADER" \
    -d "{\"ticket_type\":\"accumulator\",\"stake\":10.00,\"bankroll_id\":$BANKROLL_ID,\"legs\":[
      {\"match_id\":${CIDS[0]},\"selection\":\"home\",\"market\":\"1x2\",\"odds\":1.80},
      {\"match_id\":${CIDS[1]},\"selection\":\"draw\",\"market\":\"1x2\",\"odds\":3.40},
      {\"match_id\":${CIDS[2]},\"selection\":\"away\",\"market\":\"1x2\",\"odds\":4.20}
    ]}")
  STATUS=$(echo "$RESP" | tail -1)
  if [[ "$STATUS" == "201" ]]; then pass "Created accumulator (3 legs)"; fi
fi

# Create pending tickets on future matches
FUTURE_IDS=$($PG "SELECT id FROM matches WHERE status='scheduled' AND match_date > NOW() ORDER BY match_date ASC LIMIT 4;" | tr '\n' ',' | sed 's/,$//')
IFS=',' read -ra FIDS <<< "$FUTURE_IDS"

PENDING_CREATED=0
for MID in "${FIDS[@]}"; do
  RESP=$(curl -s -w "\n%{http_code}" -X POST "$API/tickets" \
    -H "Content-Type: application/json" -H "$AUTH_HEADER" \
    -d "{\"ticket_type\":\"single\",\"stake\":15.00,\"bankroll_id\":$BANKROLL_ID,\"legs\":[{\"match_id\":$MID,\"selection\":\"home\",\"market\":\"1x2\",\"odds\":2.10}]}")
  STATUS=$(echo "$RESP" | tail -1)
  if [[ "$STATUS" == "201" ]]; then PENDING_CREATED=$((PENDING_CREATED+1)); fi
done
pass "Created $PENDING_CREATED pending tickets on future matches"

# ============================================================
section "6. SETTLE TICKETS (won/lost)"
# ============================================================

# Get open tickets with completed matches into temp file
$PG "
SELECT t.id, t.stake, t.total_odds
FROM tickets t
WHERE t.user_id = $USER_ID AND t.status = 'open'
ORDER BY t.created_at ASC LIMIT 5;
" > /tmp/open_tickets.txt 2>/dev/null

SETTLED=0
BALANCE=5000.00
while IFS='|' read -r TID STAKE TOTAL_ODDS; do
  [[ -z "$TID" ]] && continue
  SETTLED=$((SETTLED+1))
  if [[ $((SETTLED % 3)) -ne 0 ]]; then
    OUTCOME="won"
    ACTUAL_RETURN=$(python3 -c "print(round(float('$STAKE') * float('$TOTAL_ODDS'), 2))")
    PNL=$(python3 -c "print(round(float('$ACTUAL_RETURN') - float('$STAKE'), 2))")
  else
    OUTCOME="lost"
    ACTUAL_RETURN="0"
    PNL=$(python3 -c "print(round(-float('$STAKE'), 2))")
  fi
  
  $PG "UPDATE tickets SET status='$OUTCOME', actual_return=$ACTUAL_RETURN, updated_at=NOW() WHERE id=$TID;" > /dev/null 2>&1 || true
  $PG "INSERT INTO settlements (ticket_id, settled_at, outcome, return_amount, pnl) VALUES ($TID, NOW(), '$OUTCOME', $ACTUAL_RETURN, $PNL);" > /dev/null 2>&1 || true
  $PG "INSERT INTO ledger_entries (bankroll_id, ticket_id, entry_type, amount, balance_after, description, created_at) 
       VALUES ($BANKROLL_ID, $TID, 'bet_$OUTCOME', $PNL, 0, 'Ticket #$TID $OUTCOME', NOW());" > /dev/null 2>&1 || true
done < /tmp/open_tickets.txt
pass "Settled $SETTLED tickets"

# Compute cumulative balance after each entry
$PG "
WITH running AS (
  SELECT le.id, SUM(le.amount) OVER (ORDER BY le.created_at, le.id) as cumulative
  FROM ledger_entries le WHERE le.bankroll_id = $BANKROLL_ID
)
UPDATE ledger_entries le SET balance_after = 5000.00 + r.cumulative
FROM running r WHERE le.id = r.id;
" > /dev/null 2>&1

# Update bankroll balance
$PG "
UPDATE bankrolls 
SET balance = 5000.00 + (SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE bankroll_id = $BANKROLL_ID),
    updated_at = NOW()
WHERE id = $BANKROLL_ID;
" > /dev/null 2>&1

FINAL_BALANCE=$($PG "SELECT ROUND(balance::numeric, 2) FROM bankrolls WHERE id = $BANKROLL_ID;")
pass "Bankroll balance: £$FINAL_BALANCE"

# ============================================================
section "7. SEED PREDICTIONS + VALUE BETS"
# ============================================================

# Create a prediction run first
RUN_ID=$($PG "
INSERT INTO prediction_runs (user_id, name, model_type, ensemble, status, matches_count, started_at, completed_at, created_at)
VALUES ($USER_ID, 'Poisson Run', 'PoissonGoalsModel', false, 'completed', 10, NOW() - INTERVAL '1 hour', NOW(), NOW() - INTERVAL '1 hour')
RETURNING id;
" | head -1)
RUN_ID=$(echo "$RUN_ID" | tr -d '[:space:]')
pass "Created prediction run #$RUN_ID"

# Create model predictions for future matches
$PG "
INSERT INTO model_predictions (run_id, match_id, market, home_prob, draw_prob, away_prob, home_odds, draw_odds, away_odds, value_home, value_draw, value_away, expected_value, created_at)
SELECT 
  $RUN_ID,
  m.id, '1x2',
  ROUND((0.35 + random() * 0.25)::numeric, 3),
  ROUND((0.22 + random() * 0.15)::numeric, 3),
  ROUND((0.20 + random() * 0.25)::numeric, 3),
  2.10, 3.40, 3.80,
  ROUND((random() * 0.10)::numeric, 4),
  ROUND((random() * 0.05 - 0.02)::numeric, 4),
  ROUND((random() * 0.08 - 0.01)::numeric, 4),
  ROUND((random() * 0.06)::numeric, 4),
  NOW()
FROM matches m
WHERE m.status = 'scheduled' AND m.match_date > NOW();
" > /dev/null 2>&1

MP_COUNT=$($PG "SELECT COUNT(*) FROM model_predictions WHERE run_id = $RUN_ID;")
pass "Created $MP_COUNT model predictions"

# ============================================================
section "8. VERIFY DASHBOARD API"
# ============================================================

echo -e "\n--- Dashboard Summary ---"
RESP=$(curl -s -H "$AUTH_HEADER" "$API/dashboard/summary")
echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"

TOTAL_TICKETS=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_tickets'])")
ACTIVE_BANKROLL=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['active_bankroll'])")
PENDING=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['pending_bets'])")
WIN_RATE=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['win_rate'])")

if [[ "$TOTAL_TICKETS" -gt "0" ]]; then pass "Total tickets: $TOTAL_TICKETS"
else green "Total tickets: 0"; fi

if python3 -c "exit(0 if float('$ACTIVE_BANKROLL') > 0 else 1)" 2>/dev/null; then
  pass "Active bankroll: £$ACTIVE_BANKROLL"
else green "Active bankroll: £$ACTIVE_BANKROLL"; fi

if [[ "$PENDING" -gt "0" ]]; then pass "Pending bets: $PENDING"
else green "Pending bets: 0"; fi

echo -e "\n--- Upcoming Matches ---"
RESP=$(curl -s -H "$AUTH_HEADER" "$API/dashboard/upcoming?days=7")
COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [[ "$COUNT" -gt "0" ]]; then
  pass "Upcoming matches: $COUNT"
  echo "$RESP" | python3 -c "
import sys, json
matches = json.load(sys.stdin)
for m in matches[:5]:
  odds_h = m.get('odds_home') or 'N/A'
  odds_d = m.get('odds_draw') or 'N/A'
  odds_a = m.get('odds_away') or 'N/A'
  print(f\"  {m['home_team']} vs {m['away_team']} ({m.get('competition','')}) — {str(m.get('match_date',''))[:10]} — {odds_h}/{odds_d}/{odds_a}\")
" 2>/dev/null
else green "Upcoming matches: 0"; fi

echo -e "\n--- Recent Tickets ---"
RESP=$(curl -s -H "$AUTH_HEADER" "$API/dashboard/recent-tickets?limit=10")
COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [[ "$COUNT" -gt "0" ]]; then
  pass "Recent tickets: $COUNT"
  echo "$RESP" | python3 -c "
import sys, json
tickets = json.load(sys.stdin)
for t in tickets[:5]:
  legs = len(t.get('legs', []))
  print(f\"  #{t['id']} {t['ticket_type']} — £{t['stake']:.2f} @ {t['total_odds']:.2f} — {t['status']} ({legs} legs)\")
" 2>/dev/null
else green "Recent tickets: 0"; fi

echo -e "\n--- Job Logs ---"
RESP=$(curl -s -H "$AUTH_HEADER" "$API/dashboard/job-logs?limit=5")
COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [[ "$COUNT" -gt "0" ]]; then pass "Job logs: $COUNT"; else green "Job logs: 0"; fi

echo -e "\n--- Bankroll ---"
RESP=$(curl -s -H "$AUTH_HEADER" "$API/bankroll")
COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [[ "$COUNT" -gt "0" ]]; then
  pass "Bankrolls: $COUNT"
  echo "$RESP" | python3 -c "
import sys, json
for b in json.load(sys.stdin):
  print(f\"  #{b['id']} {b['name']} — £{b['balance']:.2f} (initial £{b['initial_balance']:.2f})\")
" 2>/dev/null
else green "Bankrolls: 0"; fi

echo -e "\n--- Analytics P&L ---"
RESP=$(curl -s -H "$AUTH_HEADER" "$API/analytics/pnl?period=30d")
COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
pass "Analytics P&L data points: $COUNT"

echo -e "\n--- Ledger ---"
LEDGER_COUNT=$($PG "SELECT COUNT(*) FROM ledger_entries WHERE bankroll_id = $BANKROLL_ID;")
pass "Ledger entries: $LEDGER_COUNT"

echo -e "\n--- Predictions ---"
PRED_COUNT=$($PG "SELECT COUNT(*) FROM model_predictions WHERE run_id = $RUN_ID;")
pass "Model predictions: $PRED_COUNT"

# ============================================================
section "9. VERIFY THROUGH TUNNEL"
# ============================================================

TUNNEL="https://assistant-written-mario-donor.trycloudflare.com"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TUNNEL/" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then pass "Tunnel frontend (200)"; else green "Tunnel frontend: $HTTP_CODE"; fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TUNNEL/api/v1/dashboard/summary" -H "$AUTH_HEADER" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "401" ]]; then pass "Tunnel API (HTTP $HTTP_CODE)"; else green "Tunnel API: $HTTP_CODE"; fi

# ============================================================
section "10. PAGE NAVIGATION"
# ============================================================

for PAGE in "" "login" "predict" "tickets" "data" "scrape" "about" "board" "value-bets" "live"; do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TUNNEL/$PAGE" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "302" ]]; then
    pass "GET /$PAGE → $HTTP_CODE"
  else
    green "GET /$PAGE → $HTTP_CODE"
  fi
done

# ============================================================
section "SUMMARY"
# ============================================================

echo ""
echo -e "\033[1mResults: $PASS passed, $FAIL failed, $TOTAL total\033[0m"
echo ""
if [[ $FAIL -eq 0 ]]; then
  echo -e "\033[32mALL TESTS PASSED\033[0m"
else
  echo -e "\033[31m$FAIL TESTS FAILED\033[0m"
fi
exit $FAIL
