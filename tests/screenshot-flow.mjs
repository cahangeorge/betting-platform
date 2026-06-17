/**
 * Screenshot Flow Test
 * 
 * Seeds data → Opens browser → Captures screenshots at each phase
 * Filenames match phase names: 01-authenticate.png, 02-scrape.png, etc.
 * 
 * Usage: node tests/screenshot-flow.mjs
 */
import { chromium } from 'playwright';
import { execSync } from 'child_process';
import { mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';

const SCREENSHOTS_DIR = join(import.meta.dirname, '..', 'screenshots-tests');
const BASE_URL = 'http://127.0.0.1:8080';  // nginx — single origin for cookies
const API_URL = 'http://127.0.0.1:8001';   // direct backend for seed ops
const PG = 'podman exec bet_postgres_1 psql -U betuser -d betting_platform -t -A -F "|"';

const TODAY = new Date().toISOString().split('T')[0];
const TEST_EMAIL = `screenshot_${Date.now()}@test.com`;
const TEST_PASS = 'TestPass123!';
const TEST_NAME = 'Screenshot Test';

let authToken = null;
let bankrollId = null;

function step(msg) { console.log(`  ▸ ${msg}`); }
function info(msg) { console.log(`  ℹ ${msg}`); }

async function api(method, path, body = null) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {}),
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_URL}${path}`, opts);
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text };
}

async function pg(sql) {
  try {
    const escaped = sql.replace(/'/g, "'\\''");
    return execSync(`${PG} -c '${escaped}'`, { encoding: 'utf8', timeout: 15000 }).trim();
  } catch (e) {
    info(`DB error: ${e.stderr?.slice(0, 200) || e.message.slice(0, 200)}`);
    return '';
  }
}

async function main() {
  mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  console.log('\n══ Screenshot Flow Test ══\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  // ──────────────────────────────────────────────────────────
  // PHASE 1: Login page
  // ──────────────────────────────────────────────────────────
  console.log('══ Phase 1: Login Page ══');
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '01-login-page.png'), fullPage: true });
  info('Screenshot: 01-login-page.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 2: Authenticate — Signup then Login
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 2: Authenticate ══');

  // Signup via API
  const signupRes = await api('POST', '/api/v1/auth/signup', {
    email: TEST_EMAIL,
    password: TEST_PASS,
    name: TEST_NAME,
  });
  authToken = signupRes.json?.access_token;
  info(`Signup: ${signupRes.status}, token: ${authToken ? 'yes' : 'no'}`);

  // Create bankroll via API
  const bankRes = await api('POST', '/api/v1/bankroll', {
    name: 'Screenshot Bankroll',
    type: 'paper',
    initial_balance: 10000,
  });
  bankrollId = bankRes.json?.id;
  info(`Bankroll created: balance=$${bankRes.json?.balance ?? bankRes.json?.initial_balance} (ID: ${bankrollId}, status: ${bankRes.status})`);

  // Login via API through nginx (same origin as browser)
  const loginRes = await fetch(`${BASE_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASS }),
  });
  const loginData = await loginRes.json();
  const jwt = loginData.access_token;
  info(`Login: ${loginRes.status}, token: ${jwt ? 'yes' : 'no'}`);

  if (jwt) {
    // Set JWT cookie in browser on the same origin (nginx:8080)
    await context.addCookies([{
      name: 'access_token',
      value: jwt,
      domain: '127.0.0.1',
      path: '/',
      httpOnly: true,
    }]);
    info('JWT cookie set in browser');
  }

  // Navigate to login page and take filled form screenshot
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);

  // Fill login form for visual
  const emailInput = page.locator('input[type="email"], input[name="email"]').first();
  const passInput = page.locator('input[type="password"], input[name="password"]').first();
  if (await emailInput.isVisible().catch(() => false)) {
    await emailInput.fill(TEST_EMAIL);
    await passInput.fill(TEST_PASS);
  }

  // Screenshot the filled form
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '02-login-filled.png'), fullPage: true });
  info('Screenshot: 02-login-filled.png');

  // Navigate to dashboard — cookie should be sent to server
  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  const currentUrl = page.url();
  info(`After login URL: ${currentUrl}`);

  // Screenshot after login (should be dashboard with user data)
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '03-dashboard-empty.png'), fullPage: true });
  info('Screenshot: 03-dashboard-empty.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 3: Scrape page (before data)
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 3: Scrape Page ══');
  await page.goto(`${BASE_URL}/scrape`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '04-scrape-page-empty.png'), fullPage: true });
  info('Screenshot: 04-scrape-page-empty.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 4: Seed matches + trigger scrape via API
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 4: Seed Matches ══');

  // Seed 15 today matches
  const leagues = ['Premier League', 'Serie A', 'La Liga', 'Bundesliga', 'Ligue 1'];
  const teams = {
    'Premier League': [['Arsenal', 'Chelsea'], ['Liverpool', 'Man City'], ['Tottenham', 'Newcastle']],
    'Serie A': [['Inter Milan', 'AC Milan'], ['Juventus', 'Napoli'], ['Roma', 'Lazio']],
    'La Liga': [['Barcelona', 'Real Madrid'], ['Atletico Madrid', 'Sevilla'], ['Real Sociedad', 'Athletic Bilbao']],
    'Bundesliga': [['Bayern Munich', 'Dortmund'], ['Leipzig', 'Leverkusen'], ['Stuttgart', 'Frankfurt']],
    'Ligue 1': [['PSG', 'Marseille'], ['Lyon', 'Monaco'], ['Lille', 'Nice']],
  };

  let insertSQL = '';
  for (const league of leagues) {
    for (const [home, away] of teams[league]) {
      insertSQL += `INSERT INTO matches (home_team, away_team, status, match_date, competition, sport, season, created_at, updated_at) VALUES ('${home}', '${away}', 'scheduled', '${TODAY}', '${league}', 'football', '2024-2025', NOW(), NOW()); `;
    }
  }
  // Remove previous
  await pg(`DELETE FROM matches WHERE match_date::date = '${TODAY}'::date AND home_team IN ('Arsenal','Liverpool','Tottenham','Inter Milan','Juventus','Roma','Barcelona','Atletico Madrid','Real Sociedad','Bayern Munich','Leipzig','Stuttgart','PSG','Lyon','Lille','Arsenal','Chelsea','Man City','Newcastle','AC Milan','Napoli','Lazio','Real Madrid','Sevilla','Athletic Bilbao','Dortmund','Leverkusen','Frankfurt','Marseille','Monaco','Nice');`);
  await pg(insertSQL);
  info('15 matches seeded for today');

  // Create scrape job via API
  const scrapeRes = await api('POST', '/api/v1/data/scrape', {
    job_type: 'scrape_odds',
    params: { countries: ['England', 'Italy', 'Spain', 'Germany', 'France'], leagues: leagues },
  });
  info(`Scrape job created: ${scrapeRes.json?.id}`);

  // Execute scrape
  if (scrapeRes.json?.id) {
    await api('POST', `/api/v1/data/scrape/${scrapeRes.json.id}/execute`);
  }

  // Screenshot scrape page after job
  await page.goto(`${BASE_URL}/scrape`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '05-scrape-page-with-job.png'), fullPage: true });
  info('Screenshot: 05-scrape-page-with-job.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 5: Data page — show matches
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 5: Data Page ══');
  await page.goto(`${BASE_URL}/data`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '06-data-page-matches.png'), fullPage: true });
  info('Screenshot: 06-data-page-matches.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 6: Seed predictions + navigate to predict page
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 6: Predictions ══');

  // Seed historical matches for training
  for (const league of leagues) {
    let histSQL = '';
    for (let i = 0; i < 25; i++) {
      histSQL += `INSERT INTO matches (home_team, away_team, home_score, away_score, status, match_date, competition, sport, season, created_at, updated_at) VALUES ('Team_A_${league}_${i}', 'Team_B_${league}_${i}', ${(Math.random() * 4) | 0}, ${(Math.random() * 3) | 0}, 'completed', '${TODAY}'::date - ${365 - i}, '${league}', 'football', '2024-2025', NOW(), NOW()); `;
    }
    await pg(histSQL);
  }
  info('125 historical training matches seeded');

  // Create prediction run
  const predRes = await api('POST', '/api/v1/predictions/run', {
    league: 'Premier League',
    model_key: 'PoissonGoalsModel',
    markets: ['1x2', 'ou_2_5'],
    target_mode: 'future',
    target_limit: 15,
  });
  info(`Prediction run: ${predRes.json?.status || predRes.status}`);

  // Seed model predictions with realistic probabilities and edges
  let predSQL = `DO $$ DECLARE m RECORD; home_p DOUBLE PRECISION; draw_p DOUBLE PRECISION; away_p DOUBLE PRECISION; total_p DOUBLE PRECISION; mkt_home DOUBLE PRECISION; mkt_draw DOUBLE PRECISION; mkt_away DOUBLE PRECISION; total_mkt DOUBLE PRECISION; run_id INT; BEGIN INSERT INTO prediction_runs (name, model_type, status, created_at) VALUES ('Screenshot Run', 'PoissonGoalsModel', 'completed', NOW()) RETURNING id INTO run_id; FOR m IN SELECT id, home_team, away_team, competition FROM matches WHERE match_date::date = '${TODAY}'::date ORDER BY id LOOP home_p := 0.35 + (random() * 0.25); draw_p := 0.20 + (random() * 0.10); away_p := 1.0 - home_p - draw_p; total_p := home_p + draw_p + away_p; home_p := home_p / total_p; draw_p := draw_p / total_p; away_p := away_p / total_p; mkt_home := 0.30 + (random() * 0.30); mkt_draw := 0.20 + (random() * 0.10); mkt_away := 1.0 - mkt_home - mkt_draw; total_mkt := mkt_home + mkt_draw + mkt_away; mkt_home := mkt_home / total_mkt; mkt_draw := mkt_draw / total_mkt; mkt_away := mkt_away / total_mkt; INSERT INTO model_predictions (run_id, match_id, market, home_prob, draw_prob, away_prob, home_odds, draw_odds, away_odds, value_home, value_draw, value_away, expected_value, created_at) VALUES (run_id, m.id, '1x2', ROUND(home_p::numeric,4), ROUND(draw_p::numeric,4), ROUND(away_p::numeric,4), ROUND((1.0/(mkt_home*1.05))::numeric,2), ROUND((1.0/(mkt_draw*1.05))::numeric,2), ROUND((1.0/(mkt_away*1.05))::numeric,2), ROUND(((home_p*(1.0/(mkt_home*1.05)))-1)::numeric,4), ROUND(((draw_p*(1.0/(mkt_draw*1.05)))-1)::numeric,4), ROUND(((away_p*(1.0/(mkt_away*1.05)))-1)::numeric,4), GREATEST(((home_p*(1.0/(mkt_home*1.05)))-1), ((draw_p*(1.0/(mkt_draw*1.05)))-1), ((away_p*(1.0/(mkt_away*1.05)))-1)), NOW()); END LOOP; END $$;`;
  await pg(predSQL);
  info('Model predictions seeded with realistic edges');

  // Screenshot predict page
  await page.goto(`${BASE_URL}/predict`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '07-predict-page.png'), fullPage: true });
  info('Screenshot: 07-predict-page.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 7: Select best predictions (value bets)
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 7: Value Bets ══');
  const valueRes = await api('GET', '/api/v1/matches?status=scheduled');
  const matchList = valueRes.json?.matches || valueRes.json || [];
  const matchIds = Array.isArray(matchList) ? matchList.map(m => m.id) : [];
  info(`Found ${matchIds.length} scheduled matches for value bet lookup`);

  // Query value bets from DB
  const vbSQL = await pg(`SELECT COUNT(*) FROM model_predictions mp JOIN matches m ON mp.match_id = m.id WHERE m.match_date::date = '${TODAY}'::date AND (mp.value_home > 0 OR mp.value_draw > 0 OR mp.value_away > 0);`);
  info(`Value bets found: ${vbSQL}`);

  // Navigate to a page showing predictions
  await page.goto(`${BASE_URL}/predict`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '08-value-bets.png'), fullPage: true });
  info('Screenshot: 08-value-bets.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 8: Create tickets
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 8: Create Tickets ══');

  // Get value bets and create tickets
  const vbData = (await pg(`SELECT mp.match_id, mp.value_home, mp.value_draw, mp.value_away, mp.home_odds, mp.draw_odds, mp.away_odds, m.home_team, m.away_team FROM model_predictions mp JOIN matches m ON mp.match_id = m.id WHERE m.match_date::date = '${TODAY}'::date AND mp.market = '1x2' AND (mp.value_home > 0.02 OR mp.value_draw > 0.02 OR mp.value_away > 0.02) ORDER BY GREATEST(mp.value_home, mp.value_draw, mp.value_away) DESC LIMIT 5;`)).split('\n').filter(Boolean);

  info(`Top ${vbData.length} value bets for ticket creation`);

  let ticketCount = 0;
  const legs = [];
  for (const row of vbData) {
    const [matchId, vHome, vDraw, vAway, oHome, oDraw, oAway, home, away] = row.split('|');
    let selection = 'home', odds = oHome;
    if (parseFloat(vDraw) > parseFloat(vHome) && parseFloat(vDraw) > parseFloat(vAway)) { selection = 'draw'; odds = oDraw; }
    else if (parseFloat(vAway) > parseFloat(vHome) && parseFloat(vAway) > parseFloat(vDraw)) { selection = 'away'; odds = oAway; }

    legs.push({
      match_id: parseInt(matchId),
      selection,
      market: '1x2',
      odds: parseFloat(odds),
      home_team: home,
      away_team: away,
    });
  }

  // Create individual tickets
  for (const leg of legs.slice(0, 5)) {
    const ticketRes = await api('POST', '/api/v1/tickets', {
      ticket_type: 'single',
      legs: [{ match_id: leg.match_id, selection: leg.selection, market: leg.market, odds: leg.odds }],
      stake: 10,
    });
    if (ticketRes.status === 201 || ticketRes.status === 200) ticketCount++;
    info(`Ticket: ${leg.home_team} vs ${leg.away_team} → ${leg.selection} @ ${leg.odds} (${ticketRes.status})`);
  }

  // Create accumulator with top 3
  if (legs.length >= 3) {
    const accRes = await api('POST', '/api/v1/tickets', {
      ticket_type: 'accumulator',
      legs: legs.slice(0, 3).map(l => ({ match_id: l.match_id, selection: l.selection, market: l.market, odds: l.odds })),
      stake: 5,
    });
    if (accRes.status === 201 || accRes.status === 200) ticketCount++;
    info(`Accumulator created with 3 legs (${accRes.status})`);
  }

  info(`Total tickets created: ${ticketCount}`);

  // Screenshot tickets page
  await page.goto(`${BASE_URL}/tickets`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '09-tickets-page.png'), fullPage: true });
  info('Screenshot: 09-tickets-page.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 9: Dashboard with data
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 9: Dashboard ══');
  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '10-dashboard-with-data.png'), fullPage: true });
  info('Screenshot: 10-dashboard-with-data.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 10: Analytics
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 10: Analytics ══');
  await page.goto(`${BASE_URL}/account`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '11-account-analytics.png'), fullPage: true });
  info('Screenshot: 11-account-analytics.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 11: Board page (live odds)
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 11: Board ══');
  await page.goto(`${BASE_URL}/board`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '12-board-live-odds.png'), fullPage: true });
  info('Screenshot: 12-board-live-odds.png');

  // ──────────────────────────────────────────────────────────
  // PHASE 12: About page
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Phase 12: About ══');
  await page.goto(`${BASE_URL}/about`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: join(SCREENSHOTS_DIR, '13-about.png'), fullPage: true });
  info('Screenshot: 13-about.png');

  // ──────────────────────────────────────────────────────────
  // CLEANUP
  // ──────────────────────────────────────────────────────────
  console.log('\n══ Cleanup ══');
  await pg(`DELETE FROM ticket_legs WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id IN (SELECT id FROM users WHERE email = '${TEST_EMAIL}'));`);
  await pg(`DELETE FROM bet_placements WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id IN (SELECT id FROM users WHERE email = '${TEST_EMAIL}'));`);
  await pg(`DELETE FROM tickets WHERE user_id IN (SELECT id FROM users WHERE email = '${TEST_EMAIL}');`);
  await pg(`DELETE FROM ledger_entries WHERE bankroll_id IN (SELECT id FROM bankrolls WHERE user_id IN (SELECT id FROM users WHERE email = '${TEST_EMAIL}'));`);
  await pg(`DELETE FROM bankrolls WHERE user_id IN (SELECT id FROM users WHERE email = '${TEST_EMAIL}');`);
  await pg(`DELETE FROM model_predictions WHERE run_id IN (SELECT id FROM prediction_runs WHERE name = 'Screenshot Run');`);
  await pg(`DELETE FROM prediction_runs WHERE name = 'Screenshot Run';`);
  await pg(`DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE email = '${TEST_EMAIL}');`);
  await pg(`DELETE FROM users WHERE email = '${TEST_EMAIL}';`);
  info('Test user and data cleaned up');

  await browser.close();
  console.log('\n══ ALL SCREENSHOTS CAPTURED ══\n');
  console.log(`Screenshots saved to: ${SCREENSHOTS_DIR}/\n`);
}

main().catch(console.error);
