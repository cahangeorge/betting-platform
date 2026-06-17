#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Betfront — Full API Integration Test Suite
# Tests every major flow against the running backend (port 8001)
# Usage: bash tests/test-flows.sh [base_url]
# ═══════════════════════════════════════════════════════════════
set -uo pipefail

BASE="${1:-http://127.0.0.1:8001}"
FRONTEND="${2:-http://127.0.0.1:5174}"
PASS=0
FAIL=0
TOTAL=0
TOKEN=""
USER_ID=""

# ── Helpers ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}FAIL${NC} $1 — $2"; }
section() { echo -e "\n${CYAN}══ $1 ══${NC}"; }
assert_status() {
  local expected="$1" actual="$2" label="$3"
  if [[ "$actual" == "$expected" ]]; then pass "$label"; else fail "$label" "expected $expected, got $actual"; fi
}
assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  if echo "$haystack" | grep -q "$needle"; then pass "$label"; else fail "$label" "response missing '$needle'"; fi
}
assert_not_empty() {
  local val="$1" label="$2"
  if [[ -n "$val" && "$val" != "null" && "$val" != "" ]]; then pass "$label"; else fail "$label" "empty/null value"; fi
}
assert_json() {
  local val="$1" label="$2"
  if echo "$val" | jq . >/dev/null 2>&1; then pass "$label"; else fail "$label" "not valid JSON"; fi
}
assert_json_field() {
  local val="$1" field="$2" label="$3"
  if echo "$val" | jq -e ".$field" >/dev/null 2>&1; then pass "$label"; else fail "$label" "missing field '$field'"; fi
}
skip() {
  local label="$1" reason="$2"
  TOTAL=$((TOTAL+1))
  echo -e "  ${YELLOW}SKIP${NC} $1 — $reason"
}

# ═══════════════════════════════════════════════════════════════
section "1. HEALTH CHECK"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/health")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "200" "$STATUS" "GET /health returns 200"
assert_contains "$BODY" "ok" "Health response contains 'ok'"

# ═══════════════════════════════════════════════════════════════
section "2. SIGNUP FLOW"
# ═══════════════════════════════════════════════════════════════
EMAIL="test_$(date +%s)@betfront.com"
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/signup" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"name\":\"Test User\",\"password\":\"testpass123\"}")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "201" "$STATUS" "POST /signup returns 201"
TOKEN=$(echo "$BODY" | jq -r '.access_token // empty')
assert_not_empty "$TOKEN" "Signup returns access_token"
# Decode JWT to get user ID (base64url decode the payload)
USER_ID=$(echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq -r '.sub // empty' 2>/dev/null || echo "")
assert_not_empty "$USER_ID" "Signup token contains user ID (sub)"

# Duplicate signup should fail
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/signup" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"name\":\"Test User\",\"password\":\"testpass123\"}")
STATUS=$(echo "$RESP" | tail -1)
assert_status "409" "$STATUS" "Duplicate signup returns 409"

# Weak password should fail
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/signup" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"weak@test.com\",\"name\":\"Weak\",\"password\":\"short\"}")
STATUS=$(echo "$RESP" | tail -1)
assert_status "422" "$STATUS" "Weak password returns 422"

# ═══════════════════════════════════════════════════════════════
section "3. LOGIN FLOW"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"testpass123\"}")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "200" "$STATUS" "POST /login returns 200"
LOGIN_TOKEN=$(echo "$BODY" | jq -r '.access_token // empty')
assert_not_empty "$LOGIN_TOKEN" "Login returns access_token"

# Wrong password should fail
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"wrongpassword\"}")
STATUS=$(echo "$RESP" | tail -1)
assert_status "401" "$STATUS" "Wrong password returns 401"

# Non-existent user should fail
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"nonexistent@test.com\",\"password\":\"testpass123\"}")
STATUS=$(echo "$RESP" | tail -1)
assert_status "401" "$STATUS" "Non-existent user returns 401"

# Use the signup token for subsequent requests
AUTH_HEADER="Authorization: Bearer $TOKEN"

# ═══════════════════════════════════════════════════════════════
section "4. GET ME (Authenticated)"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/auth/me" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "200" "$STATUS" "GET /me returns 200"
assert_contains "$BODY" "$EMAIL" "GET /me returns correct email"

# Without token should fail
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/auth/me")
STATUS=$(echo "$RESP" | tail -1)
assert_status "401" "$STATUS" "GET /me without token returns 401"

# ═══════════════════════════════════════════════════════════════
section "5. MATCHES FLOW"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/matches" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "200" "$STATUS" "GET /matches returns 200"

# Filter by league
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/matches?league=Premier+League" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /matches?league=Premier+League returns 200"

# Filter by status
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/matches?status=scheduled" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /matches?status=scheduled returns 200"

# Get single match (if matches exist)
MATCHES_BODY=$(echo "$BODY" | jq -r '.matches // .items // .')
MATCH_COUNT=$(echo "$MATCHES_BODY" | jq 'length // 0')
if [[ "$MATCH_COUNT" -gt 0 ]]; then
  MATCH_ID=$(echo "$MATCHES_BODY" | jq -r '.[0].id')
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/matches/$MATCH_ID" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "200" "$STATUS" "GET /matches/$MATCH_ID returns 200"

  # Get odds for match
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/matches/$MATCH_ID/odds" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "200" "$STATUS" "GET /matches/$MATCH_ID/odds returns 200"
else
  echo -e "  ${YELLOW}SKIP${NC} No matches in DB — single match & odds tests skipped"
fi

# Non-existent match
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/matches/99999" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "404" "$STATUS" "GET /matches/99999 returns 404"

# ═══════════════════════════════════════════════════════════════
section "6. PREDICTIONS FLOW"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/predictions/catalog" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "200" "$STATUS" "GET /predictions/catalog returns 200"
CATALOG_SIZE=$(echo "$BODY" | jq 'length // 0')
echo -e "  ${YELLOW}INFO${NC} Catalog has $CATALOG_SIZE models"

# List prediction runs
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/predictions/runs" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /predictions/runs returns 200"

# ═══════════════════════════════════════════════════════════════
section "7. BANKROLL FLOW"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/bankroll" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "200" "$STATUS" "GET /bankroll returns 200"

# Create a bankroll
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/bankroll" \
  -H "Content-Type: application/json" -H "$AUTH_HEADER" \
  -d '{"name":"Test Bankroll","type":"paper","currency":"EUR","initial_balance":10000}')
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "201" "$STATUS" "POST /bankroll creates bankroll (201)"
BANKROLL_ID=$(echo "$BODY" | jq -r '.id // empty')
assert_not_empty "$BANKROLL_ID" "Created bankroll has ID"

if [[ -n "$BANKROLL_ID" ]]; then
  # Get the created bankroll
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/bankroll/$BANKROLL_ID" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -1)
  assert_status "200" "$STATUS" "GET /bankroll/$BANKROLL_ID returns 200"
  assert_contains "$BODY" "Test Bankroll" "Bankroll name matches"
  assert_contains "$BODY" "10000" "Bankroll balance is 10000"

  # List accounts for bankroll
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/bankroll/$BANKROLL_ID/accounts" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "200" "$STATUS" "GET /bankroll/$BANKROLL_ID/accounts returns 200"

  # Get ledger for bankroll
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/bankroll/$BANKROLL_ID/ledger" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "200" "$STATUS" "GET /bankroll/$BANKROLL_ID/ledger returns 200"

  # Delete bankroll
  RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE/api/v1/bankroll/$BANKROLL_ID" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "204" "$STATUS" "DELETE /bankroll/$BANKROLL_ID returns 204"

  # Verify deleted
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/bankroll/$BANKROLL_ID" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "404" "$STATUS" "Deleted bankroll returns 404"
fi

# ═══════════════════════════════════════════════════════════════
section "8. TICKETS FLOW"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/tickets" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /tickets returns 200"

# ═══════════════════════════════════════════════════════════════
section "9. DATA / SCRAPING FLOW"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/data/scrape" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /data/scrape returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/data/datasets" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /data/datasets returns 200"

# ═══════════════════════════════════════════════════════════════
section "10. SCHEDULED JOBS FLOW"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/jobs" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
assert_status "200" "$STATUS" "GET /jobs returns 200"

# Create a scheduled job (may require admin)
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/jobs" \
  -H "Content-Type: application/json" -H "$AUTH_HEADER" \
  -d '{"name":"Test Job","cron_expression":"0 */6 * * *","task_type":"scrape_odds","params":{}}')
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$STATUS" == "403" ]]; then
  pass "POST /jobs correctly requires admin role (403)"
else
  assert_status "201" "$STATUS" "POST /jobs creates job (201)"
fi
JOB_ID=$(echo "$BODY" | jq -r '.id // empty')
if [[ "$STATUS" != "403" ]]; then
  assert_not_empty "$JOB_ID" "Created job has ID"
fi

if [[ -n "$JOB_ID" && "$JOB_ID" != "null" ]]; then
  # Get the created job
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/jobs/$JOB_ID" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -1)
  assert_status "200" "$STATUS" "GET /jobs/$JOB_ID returns 200"
  assert_contains "$BODY" "Test Job" "Job name matches"

  # Toggle the job
  RESP=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE/api/v1/jobs/$JOB_ID/toggle" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -1)
  assert_status "200" "$STATUS" "PATCH /jobs/$JOB_ID/toggle returns 200"
  IS_ENABLED=$(echo "$BODY" | jq -r '.is_enabled // empty')
  echo -e "  ${YELLOW}INFO${NC} Job toggle: is_enabled=$IS_ENABLED"
fi

# ═══════════════════════════════════════════════════════════════
section "11. LOGOUT FLOW"
# ═══════════════════════════════════════════════════════════════
# Logout clears httpOnly cookies but doesn't invalidate Bearer tokens (stateless JWT)
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/auth/logout" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "POST /logout returns 200"

# Cookie-based auth should be cleared (test with cookie jar)
COOKIES=$(mktemp)
curl -s -c "$COOKIES" -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"testpass123\"}" > /dev/null
RESP=$(curl -s -w "\n%{http_code}" -b "$COOKIES" "$BASE/api/v1/auth/me")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /me with cookie works after login"

# Now logout with cookie
curl -s -c "$COOKIES" -b "$COOKIES" -X POST "$BASE/api/v1/auth/logout" > /dev/null
RESP=$(curl -s -w "\n%{http_code}" -b "$COOKIES" "$BASE/api/v1/auth/me")
STATUS=$(echo "$RESP" | tail -1)
assert_status "401" "$STATUS" "GET /me with cleared cookie returns 401 after logout"
rm -f "$COOKIES"

# ═══════════════════════════════════════════════════════════════
section "12. CORS VERIFICATION"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -sI -X OPTIONS "$BASE/api/v1/auth/login" \
  -H "Origin: http://localhost:5174" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type")
ALLOW_ORIGIN=$(echo "$RESP" | grep -i "access-control-allow-origin" | tr -d '\r')
if echo "$ALLOW_ORIGIN" | grep -q "http://localhost:5174"; then
  pass "CORS allows http://localhost:5174"
else
  fail "CORS allows http://localhost:5174" "got: $ALLOW_ORIGIN"
fi

ALLOW_CREDS=$(echo "$RESP" | grep -i "access-control-allow-credentials" | tr -d '\r')
if echo "$ALLOW_CREDS" | grep -q "true"; then
  pass "CORS credentials allowed"
else
  fail "CORS credentials allowed" "got: $ALLOW_CREDS"
fi

# ═══════════════════════════════════════════════════════════════
section "13. FRONTEND ACCESSIBILITY"
# ═══════════════════════════════════════════════════════════════
RESP=$(curl -s -w "\n%{http_code}" "$FRONTEND/")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "Frontend / returns 200"
CHECK=$(curl -s "$FRONTEND/" | head -c 2000)
if echo "$CHECK" | grep -qi "betfront"; then pass "Frontend contains 'Betfront'"; else fail "Frontend contains 'Betfront'" "first 2000 chars: $(echo "$CHECK" | head -c 200)"; fi

RESP=$(curl -s -w "\n%{http_code}" "$FRONTEND/login")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "Frontend /login returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$FRONTEND/signup")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "Frontend /signup returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$FRONTEND/board")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "Frontend /board returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$FRONTEND/about")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "Frontend /about returns 200"

# Check no-cache headers on HTML
CACHE=$(curl -sI "$FRONTEND/login" | grep -i "cache-control" | tr -d '\r')
if echo "$CACHE" | grep -q "no-store"; then
  pass "HTML pages have no-store cache-control"
else
  fail "HTML pages have no-store cache-control" "got: $CACHE"
fi

# ═══════════════════════════════════════════════════════════════
# SECTION 14: DASHBOARD ENDPOINTS
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}── Dashboard ──${NC}"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/dashboard/summary" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "200" "$STATUS" "GET /dashboard/summary returns 200"
assert_json "$BODY" "Dashboard summary is valid JSON"
assert_json_field "$BODY" "total_matches" "Summary has total_matches"
assert_json_field "$BODY" "total_pnl" "Summary has total_pnl"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/dashboard/recent-tickets" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /dashboard/recent-tickets returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/dashboard/upcoming" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /dashboard/upcoming returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/dashboard/job-logs" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /dashboard/job-logs returns 200"

# ═══════════════════════════════════════════════════════════════
# SECTION 15: CATALOG ENDPOINTS
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}── Catalog ──${NC}"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/catalog/countries" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "200" "$STATUS" "GET /catalog/countries returns 200"
assert_json "$BODY" "Catalog countries is valid JSON"

COUNTRY_COUNT=$(echo "$BODY" | jq 'length' 2>/dev/null || echo "0")
if [[ "$COUNTRY_COUNT" -gt 0 ]]; then
  pass "Catalog returns $COUNTRY_COUNT countries"
else
  fail "Catalog returns countries" "got 0 countries"
fi

# Get first country name
FIRST_COUNTRY=$(echo "$BODY" | jq -r '.[0].name // empty' 2>/dev/null)
if [[ -n "$FIRST_COUNTRY" ]]; then
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/catalog/leagues?country=$FIRST_COUNTRY" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "200" "$STATUS" "GET /catalog/leagues?country=$FIRST_COUNTRY returns 200"
else
  skip "GET /catalog/leagues" "No countries to test with"
fi

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/catalog/leagues/all" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /catalog/leagues/all returns 200"

# ═══════════════════════════════════════════════════════════════
# SECTION 16: ANALYTICS ENDPOINTS
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}── Analytics ──${NC}"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/analytics/pnl" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /analytics/pnl returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/analytics/pnl/by-league" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /analytics/pnl/by-league returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/analytics/pnl/by-model" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /analytics/pnl/by-model returns 200"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/analytics/equity-curve" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
assert_status "200" "$STATUS" "GET /analytics/equity-curve returns 200"

# ═══════════════════════════════════════════════════════════════
# SECTION 17: STRATEGIES ENDPOINTS
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}── Strategies ──${NC}"

RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/strategies" -H "$AUTH_HEADER")
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "200" "$STATUS" "GET /strategies returns 200"
assert_json "$BODY" "Strategies list is valid JSON"

# Create a strategy
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/strategies" \
  -H "Content-Type: application/json" -H "$AUTH_HEADER" \
  -d '{"name":"Test Poisson","model_type":"poisson","description":"Test strategy","parameters":{"home_advantage":1.2},"is_active":true}')
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
assert_status "201" "$STATUS" "POST /strategies creates strategy (201)"
STRATEGY_ID=$(echo "$BODY" | jq -r '.id // empty')
assert_not_empty "$STRATEGY_ID" "Created strategy has ID"

if [[ -n "$STRATEGY_ID" && "$STRATEGY_ID" != "null" ]]; then
  # Get the strategy
  RESP=$(curl -s -w "\n%{http_code}" "$BASE/api/v1/strategies/$STRATEGY_ID" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | sed '$d')
  assert_status "200" "$STATUS" "GET /strategies/$STRATEGY_ID returns 200"
  assert_contains "$BODY" "Test Poisson" "Strategy name matches"

  # Update the strategy (PUT, not PATCH)
  RESP=$(curl -s -w "\n%{http_code}" -X PUT "$BASE/api/v1/strategies/$STRATEGY_ID" \
    -H "Content-Type: application/json" -H "$AUTH_HEADER" \
    -d '{"name":"Updated Poisson","is_active":false}')
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "200" "$STATUS" "PUT /strategies/$STRATEGY_ID returns 200"

  # Delete the strategy
  RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE/api/v1/strategies/$STRATEGY_ID" -H "$AUTH_HEADER")
  STATUS=$(echo "$RESP" | tail -1)
  assert_status "204" "$STATUS" "DELETE /strategies/$STRATEGY_ID returns 204"
else
  skip "GET/PATCH/DELETE strategy" "No strategy ID from create"
fi

# ═══════════════════════════════════════════════════════════════
# SECTION 18: NEW FRONTEND PAGES
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}── New Frontend Pages ──${NC}"

for PAGE in scrape predict; do
  RESP=$(curl -s -w "\n%{http_code}" "$FRONTEND/$PAGE")
  STATUS=$(echo "$RESP" | tail -1)
  # Pages behind auth redirect to /login (302) — that's expected
  if [[ "$STATUS" == "302" ]]; then
    pass "Frontend /$PAGE returns 302 (auth redirect, correct)"
  else
    assert_status "200" "$STATUS" "Frontend /$PAGE returns 200"
  fi
done

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}══════════════════════════════════════${NC}"
echo -e "${CYAN}  RESULTS: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, $TOTAL total"
echo -e "${CYAN}══════════════════════════════════════${NC}"

if [[ $FAIL -gt 0 ]]; then
  echo -e "\n${RED}Some tests failed.${NC}"
  exit 1
else
  echo -e "\n${GREEN}All tests passed!${NC}"
  exit 0
fi
