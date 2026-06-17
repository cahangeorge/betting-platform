# Frontend Real-Backend E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Playwright E2E harness in `frontend/` that runs a stable hybrid suite against the real backend and an opt-in live scrape-to-ticket suite against the full live chain.

**Architecture:** The frontend owns the browser harness and Playwright config, while helper modules under `frontend/tests/e2e/helpers/` manage backend API setup, deterministic hybrid seeding, live scrape orchestration, and cleanup. The default suite runs browser flows against a running backend with deterministic fallback data; the live suite uses the same harness but refuses fallback and fails honestly when the scrape bridges or upstream chain break.

**Tech Stack:** SvelteKit 2, Playwright, Node 22+, bash/HTTP backend health assumptions, PostgreSQL-backed FastAPI backend accessed through public APIs plus targeted SQL seeding helpers.

---

## File Map

- Create: `frontend/playwright.config.ts`
  - Playwright config for hybrid and live suites, frontend web server, env plumbing, retries, traces, and per-suite discovery.
- Modify: `frontend/package.json`
  - Add `test:e2e` and `test:e2e:live` scripts.
- Create: `frontend/tests/e2e/helpers/backend.ts`
  - Low-level HTTP helpers, health checks, polling, env parsing, backend assertions.
- Create: `frontend/tests/e2e/helpers/auth.ts`
  - Fresh user signup/login helpers, browser cookie/session establishment, bankroll bootstrap.
- Create: `frontend/tests/e2e/helpers/cleanup.ts`
  - Cleanup for test-created users, tickets, bankrolls, sessions, and deterministic seeded records.
- Create: `frontend/tests/e2e/helpers/seed.ts`
  - Deterministic hybrid setup for matches, historical training data, predictions, and any required dashboard/ticket state.
- Create: `frontend/tests/e2e/helpers/scrape.ts`
  - Scrape job creation/execution/polling and ingestion verification for both hybrid honesty checks and live suite.
- Create: `frontend/tests/e2e/helpers/types.ts`
  - Shared helper-side types for test context, created entities, env config, and seeded resources.
- Create: `frontend/tests/e2e/hybrid/auth-dashboard.spec.ts`
  - Authenticated dashboard flow.
- Create: `frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts`
  - Dashboard -> add to slip -> tickets -> place ticket flow.
- Create: `frontend/tests/e2e/hybrid/predict-slip-ticket.spec.ts`
  - Predict -> add result -> tickets -> place ticket flow.
- Create: `frontend/tests/e2e/hybrid/live-value-data.spec.ts`
  - `/live`, `/value-bets`, `/data` honesty and real-backend content checks.
- Create: `frontend/tests/e2e/hybrid/scrape-job-honesty.spec.ts`
  - Scrape page status truthfulness and failure/success surfacing.
- Create: `frontend/tests/e2e/live/live-scrape-predict-ticket.spec.ts`
  - Full live scrape -> predict -> add to slip -> place ticket flow.
- Optionally create: `frontend/tests/e2e/README.md`
  - Short local run contract for hybrid vs live mode if setup details become non-obvious.

## Task 1: Install the Playwright Harness Skeleton

**Files:**
- Create: `frontend/playwright.config.ts`
- Modify: `frontend/package.json`
- Test: `frontend/playwright.config.ts` via `npx playwright test --list`

- [ ] **Step 1: Write the failing config discovery test**

Create a shell check command expectation first by attempting to list tests before config exists:

Run: `cd frontend && npx playwright test --list`
Expected: FAIL with missing config or no tests found.

- [ ] **Step 2: Create the Playwright config with hybrid/live suite discovery**

Add `frontend/playwright.config.ts`:

```ts
import { defineConfig } from '@playwright/test';

const frontendUrl = process.env.E2E_FRONTEND_URL || 'http://127.0.0.1:5175';
const backendUrl = process.env.E2E_BACKEND_URL || 'http://127.0.0.1:8001';
const isLive = process.env.E2E_MODE === 'live';

export default defineConfig({
	testDir: './tests/e2e',
	fullyParallel: false,
	workers: 1,
	retries: isLive ? 0 : 1,
	timeout: isLive ? 180_000 : 90_000,
	expect: {
		timeout: 10_000
	},
	use: {
		baseURL: frontendUrl,
		trace: 'retain-on-failure',
		screenshot: 'only-on-failure',
		video: 'off'
	},
	webServer: {
		command: 'npm run dev',
		url: frontendUrl,
		reuseExistingServer: true,
		cwd: '.',
		timeout: 120_000,
		env: {
			...process.env,
			E2E_FRONTEND_URL: frontendUrl,
			E2E_BACKEND_URL: backendUrl
		}
	},
	projects: [
		{
			name: 'chromium-hybrid',
			testMatch: /hybrid\/.*\.spec\.ts/,
			use: {
				browserName: 'chromium'
			}
		},
		{
			name: 'chromium-live',
			testMatch: /live\/.*\.spec\.ts/,
			grep: /@live/,
			use: {
				browserName: 'chromium'
			}
		}
	],
	reporter: [['list']]
});
```

- [ ] **Step 3: Add the E2E scripts**

Update `frontend/package.json` scripts:

```json
{
  "scripts": {
    "dev": "vite dev --host 127.0.0.1 --port 5175 --strictPort",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
    "test:e2e": "E2E_MODE=hybrid npx playwright test --project=chromium-hybrid",
    "test:e2e:live": "E2E_MODE=live npx playwright test --project=chromium-live"
  }
}
```

- [ ] **Step 4: Run test discovery to verify the harness is wired**

Run: `cd frontend && npx playwright test --list`
Expected: PASS, config loads, hybrid/live projects are recognized even if specs are not implemented yet.

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/package.json
git commit -m "test: add Playwright e2e harness skeleton"
```

## Task 2: Build Shared Backend and Auth Helpers

**Files:**
- Create: `frontend/tests/e2e/helpers/types.ts`
- Create: `frontend/tests/e2e/helpers/backend.ts`
- Create: `frontend/tests/e2e/helpers/auth.ts`
- Test: `frontend/tests/e2e/hybrid/auth-dashboard.spec.ts`

- [ ] **Step 1: Write the first failing hybrid auth smoke test**

Create `frontend/tests/e2e/hybrid/auth-dashboard.spec.ts`:

```ts
import { expect, test } from '@playwright/test';

test('authenticated user can reach dashboard', async ({ page }) => {
	await page.goto('/login');
	await expect(page).toHaveURL(/\/login$/);
});
```

Run: `cd frontend && npx playwright test tests/e2e/hybrid/auth-dashboard.spec.ts --project=chromium-hybrid`
Expected: FAIL later when the test is expanded to require real auth helpers; initially it may pass trivially, so extend in the next step before implementing helpers.

- [ ] **Step 2: Expand the test so it genuinely needs auth helpers**

Replace the spec with:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';

test('authenticated user can reach dashboard', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);
	await page.goto('/');
	await expect(page.getByText(session.user.name)).toBeVisible();
	await expect(page.getByText(/dashboard/i)).toBeVisible();
});
```

Run: `cd frontend && npx playwright test tests/e2e/hybrid/auth-dashboard.spec.ts --project=chromium-hybrid`
Expected: FAIL with module/function missing.

- [ ] **Step 3: Create shared helper-side types**

Add `frontend/tests/e2e/helpers/types.ts`:

```ts
export interface E2EConfig {
	frontendUrl: string;
	backendUrl: string;
	mode: 'hybrid' | 'live';
	liveScrapeTimeoutMs: number;
}

export interface TestUser {
	email: string;
	name: string;
	password: string;
}

export interface AuthSession {
	user: {
		id: number;
		email: string;
		name: string;
	};
	token: string;
	bankrollId: number;
	namespace: string;
}
```

- [ ] **Step 4: Create backend env and HTTP helpers**

Add `frontend/tests/e2e/helpers/backend.ts`:

```ts
import { expect } from '@playwright/test';
import type { E2EConfig } from './types';

export function getE2EConfig(): E2EConfig {
	return {
		frontendUrl: process.env.E2E_FRONTEND_URL || 'http://127.0.0.1:5175',
		backendUrl: process.env.E2E_BACKEND_URL || 'http://127.0.0.1:8001',
		mode: process.env.E2E_MODE === 'live' ? 'live' : 'hybrid',
		liveScrapeTimeoutMs: Number(process.env.E2E_LIVE_SCRAPE_TIMEOUT_SECONDS || '240') * 1000
	};
}

export async function api<T>(
	path: string,
	init?: RequestInit,
	token?: string
): Promise<{ status: number; json: T }> {
	const { backendUrl } = getE2EConfig();
	const response = await fetch(`${backendUrl}${path}`, {
		...init,
		headers: {
			'Content-Type': 'application/json',
			...(token ? { Authorization: `Bearer ${token}` } : {}),
			...(init?.headers || {})
		}
	});
	const json = (await response.json().catch(() => ({}))) as T;
	return { status: response.status, json };
}

export async function assertBackendHealthy(): Promise<void> {
	const { status } = await api<{ status?: string }>('/health');
	expect(status).toBe(200);
}

export async function poll<T>(
	check: () => Promise<T>,
	isDone: (value: T) => boolean,
	timeoutMs = 30_000,
	intervalMs = 1_000
): Promise<T> {
	const started = Date.now();
	while (true) {
		const value = await check();
		if (isDone(value)) return value;
		if (Date.now() - started > timeoutMs) {
			throw new Error(`Polling timed out after ${timeoutMs}ms`);
		}
		await new Promise((resolve) => setTimeout(resolve, intervalMs));
	}
}
```

- [ ] **Step 5: Create auth/bootstrap helper**

Add `frontend/tests/e2e/helpers/auth.ts`:

```ts
import type { BrowserContext } from '@playwright/test';
import { api, assertBackendHealthy, getE2EConfig } from './backend';
import type { AuthSession, TestUser } from './types';

function makeUser(namespace: string): TestUser {
	return {
		email: `${namespace}@betfront-e2e.local`,
		name: `E2E ${namespace}`,
		password: 'TestPass123!'
	};
}

export async function createAuthenticatedSession(context: BrowserContext): Promise<AuthSession> {
	await assertBackendHealthy();

	const namespace = `e2e_${Date.now()}`;
	const user = makeUser(namespace);

	const signup = await api<{ access_token?: string; user?: { id: number; email: string; name: string } }>(
		'/api/v1/auth/signup',
		{
			method: 'POST',
			body: JSON.stringify(user)
		}
	);

	if (signup.status !== 201 || !signup.json.access_token) {
		throw new Error(`Signup failed with status ${signup.status}`);
	}

	const token = signup.json.access_token;
	const me = await api<{ id: number; email: string; name: string }>('/api/v1/auth/me', undefined, token);
	if (me.status !== 200) {
		throw new Error(`Auth verification failed with status ${me.status}`);
	}

	const bankroll = await api<{ id: number }>(
		'/api/v1/bankroll',
		{
			method: 'POST',
			body: JSON.stringify({
				name: `Bankroll ${namespace}`,
				type: 'paper',
				initial_balance: 10000
			})
		},
		token
	);

	if (bankroll.status !== 201 || !bankroll.json.id) {
		throw new Error(`Bankroll bootstrap failed with status ${bankroll.status}`);
	}

	const { frontendUrl } = getE2EConfig();
	const hostname = new URL(frontendUrl).hostname;
	await context.addCookies([
		{
			name: 'access_token',
			value: token,
			domain: hostname,
			path: '/',
			httpOnly: true,
			sameSite: 'Lax'
		}
	]);

	return {
		user: me.json,
		token,
		bankrollId: bankroll.json.id,
		namespace
	};
}
```

- [ ] **Step 6: Run the auth test to verify it passes**

Run: `cd frontend && npx playwright test tests/e2e/hybrid/auth-dashboard.spec.ts --project=chromium-hybrid`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/tests/e2e/helpers/types.ts frontend/tests/e2e/helpers/backend.ts frontend/tests/e2e/helpers/auth.ts frontend/tests/e2e/hybrid/auth-dashboard.spec.ts
git commit -m "test: add real-backend auth helpers for e2e"
```

## Task 3: Add Cleanup and Deterministic Hybrid Seeding

**Files:**
- Create: `frontend/tests/e2e/helpers/cleanup.ts`
- Create: `frontend/tests/e2e/helpers/seed.ts`
- Modify: `frontend/tests/e2e/helpers/types.ts`
- Test: `frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts`

- [ ] **Step 1: Write the failing dashboard-to-ticket flow test**

Create `frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts`:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { ensureHybridTicketableData } from '../helpers/seed';

test('dashboard selection survives to tickets and places a ticket', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	await ensureHybridTicketableData(session);

	await page.goto('/');
	await expect(page.getByRole('button', { name: /review slip/i })).toBeVisible();
});
```

Run: `cd frontend && npx playwright test tests/e2e/hybrid/dashboard-slip-ticket.spec.ts --project=chromium-hybrid`
Expected: FAIL with missing seed helper.

- [ ] **Step 2: Extend helper types for cleanup and seeded resources**

Update `frontend/tests/e2e/helpers/types.ts`:

```ts
export interface SeededMatch {
	id: number;
	home_team: string;
	away_team: string;
	competition: string;
}

export interface HybridSeedResult {
	matches: SeededMatch[];
	predictionRunId?: number;
}
```

- [ ] **Step 3: Add deterministic seeding helper**

Add `frontend/tests/e2e/helpers/seed.ts`:

```ts
import { api } from './backend';
import type { AuthSession, HybridSeedResult } from './types';
import { execFileSync } from 'node:child_process';

function runSql(sql: string): void {
	execFileSync('bash', ['-lc', `podman exec bet_postgres_1 psql -U betuser -d betting_platform -v ON_ERROR_STOP=1 -c "${sql.replace(/"/g, '\\"')}"`], {
		stdio: 'inherit'
	});
}

export async function ensureHybridTicketableData(session: AuthSession): Promise<HybridSeedResult> {
	const namespace = session.namespace;
	const today = new Date().toISOString().slice(0, 10);

	runSql(`
		INSERT INTO matches (home_team, away_team, status, match_date, competition, sport, season, created_at, updated_at)
		VALUES
			('${namespace}_Arsenal', '${namespace}_Chelsea', 'scheduled', '${today} 15:00:00+00', 'Premier League', 'football', '2025-2026', NOW(), NOW()),
			('${namespace}_Liverpool', '${namespace}_City', 'scheduled', '${today} 17:00:00+00', 'Premier League', 'football', '2025-2026', NOW(), NOW()),
			('${namespace}_Inter', '${namespace}_Milan', 'scheduled', '${today} 19:00:00+00', 'Serie A', 'football', '2025-2026', NOW(), NOW());
	`);

	runSql(`
		INSERT INTO odds_entries (match_id, bookmaker, market, home_odds, draw_odds, away_odds, timestamp)
		SELECT id, 'e2e-seed', '1x2', 2.10, 3.40, 3.10, NOW()
		FROM matches
		WHERE home_team LIKE '${namespace}_%';
	`);

	const matches = await api<Array<{ id: number; home_team: string; away_team: string; competition: string }>>(
		'/api/v1/matches?status=scheduled',
		undefined,
		session.token
	);

	return {
		matches: (matches.json || []).filter((match) => match.home_team.startsWith(namespace))
	};
}
```

- [ ] **Step 4: Add cleanup helper**

Add `frontend/tests/e2e/helpers/cleanup.ts`:

```ts
import { execFileSync } from 'node:child_process';
import type { AuthSession } from './types';

export async function cleanupSession(session: AuthSession): Promise<void> {
	const namespace = session.namespace;
	execFileSync('bash', ['-lc', `
		podman exec bet_postgres_1 psql -U betuser -d betting_platform <<'SQL'
		DELETE FROM ticket_legs WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
		DELETE FROM settlements WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
		DELETE FROM bet_placements WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
		DELETE FROM tickets WHERE user_id = ${session.user.id};
		DELETE FROM ledger_entries WHERE bankroll_id IN (SELECT id FROM bankrolls WHERE user_id = ${session.user.id});
		DELETE FROM bankrolls WHERE user_id = ${session.user.id};
		DELETE FROM sessions WHERE user_id = ${session.user.id};
		DELETE FROM odds_entries WHERE bookmaker = 'e2e-seed' AND match_id IN (SELECT id FROM matches WHERE home_team LIKE '${namespace}_%');
		DELETE FROM matches WHERE home_team LIKE '${namespace}_%';
		DELETE FROM users WHERE id = ${session.user.id};
SQL
	`], { stdio: 'inherit' });
}
```

- [ ] **Step 5: Make the test use setup and cleanup**

Update `frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts`:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';
import { ensureHybridTicketableData } from '../helpers/seed';

test('dashboard selection survives to tickets and places a ticket', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		await ensureHybridTicketableData(session);
		await page.goto('/');
		await expect(page.getByText(/dashboard/i)).toBeVisible();
		await expect(page.getByRole('button', { name: /review slip/i })).toBeVisible();
	} finally {
		await cleanupSession(session);
	}
});
```

- [ ] **Step 6: Run the dashboard flow to verify setup works**

Run: `cd frontend && npx playwright test tests/e2e/hybrid/dashboard-slip-ticket.spec.ts --project=chromium-hybrid`
Expected: PASS or advance far enough that the next missing UI assertions are real flow failures instead of setup failures.

- [ ] **Step 7: Commit**

```bash
git add frontend/tests/e2e/helpers/types.ts frontend/tests/e2e/helpers/seed.ts frontend/tests/e2e/helpers/cleanup.ts frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts
git commit -m "test: add deterministic hybrid e2e seeding"
```

## Task 4: Finish the Dashboard -> Betslip -> Ticket Browser Flow

**Files:**
- Modify: `frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts`
- Test: `frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts`

- [ ] **Step 1: Tighten the flow test to a real browser interaction**

Update `frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts`:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';
import { ensureHybridTicketableData } from '../helpers/seed';

test('dashboard selection survives to tickets and places a ticket', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		await ensureHybridTicketableData(session);

		await page.goto('/');
		await expect(page.getByText(/upcoming matches/i)).toBeVisible();

		await page.getByRole('button', { name: /^2\.10$/ }).first().click();
		await page.getByRole('link', { name: /review slip/i }).click();

		await expect(page).toHaveURL(/\/tickets$/);
		await expect(page.getByText(/place bet/i)).toBeVisible();
		await page.getByLabel(/stake/i).fill('10');
		await page.getByRole('button', { name: /place ticket/i }).click();

		await expect(page.getByText(/active tickets/i)).toBeVisible();
	} finally {
		await cleanupSession(session);
	}
});
```

- [ ] **Step 2: Run the test to verify it fails on a real missing selector or behavior**

Run: `cd frontend && npx playwright test tests/e2e/hybrid/dashboard-slip-ticket.spec.ts --project=chromium-hybrid`
Expected: FAIL with a concrete locator/behavior issue if the flow is not yet aligned.

- [ ] **Step 3: Adjust selectors only inside the test to match current UI semantics**

Refine the exact locators after observing the real DOM. Acceptable replacements:

```ts
await page.getByText(/^2\.10$/).first().click();
await page.getByRole('button', { name: /review ticket/i }).click();
await page.getByRole('button', { name: /place ticket|place bet/i }).click();
```

Do not change app code in this task unless the browser flow reveals a real regression.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx playwright test tests/e2e/hybrid/dashboard-slip-ticket.spec.ts --project=chromium-hybrid`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/e2e/hybrid/dashboard-slip-ticket.spec.ts
git commit -m "test: cover dashboard to ticket e2e flow"
```

## Task 5: Add Predict -> Slip -> Ticket Hybrid Coverage

**Files:**
- Modify: `frontend/tests/e2e/helpers/seed.ts`
- Create: `frontend/tests/e2e/hybrid/predict-slip-ticket.spec.ts`
- Test: `frontend/tests/e2e/hybrid/predict-slip-ticket.spec.ts`

- [ ] **Step 1: Write the failing predict flow test**

Create `frontend/tests/e2e/hybrid/predict-slip-ticket.spec.ts`:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';
import { ensureHybridPredictionData } from '../helpers/seed';

test('prediction result can be added to slip and placed as a ticket', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		await ensureHybridPredictionData(session);
		await page.goto('/predict');
		await expect(page.getByText(/results/i)).toBeVisible();
	} finally {
		await cleanupSession(session);
	}
});
```

Run: `cd frontend && npx playwright test tests/e2e/hybrid/predict-slip-ticket.spec.ts --project=chromium-hybrid`
Expected: FAIL with missing seed helper.

- [ ] **Step 2: Add prediction seeding helper**

Extend `frontend/tests/e2e/helpers/seed.ts`:

```ts
export async function ensureHybridPredictionData(session: AuthSession): Promise<HybridSeedResult> {
	const seeded = await ensureHybridTicketableData(session);
	const namespace = session.namespace;

	runSql(`
		INSERT INTO prediction_runs (name, model_type, status, created_at)
		VALUES ('${namespace}_run', 'PoissonGoalsModel', 'completed', NOW());
	`);

	runSql(`
		INSERT INTO model_predictions (run_id, match_id, market, home_prob, draw_prob, away_prob, home_odds, draw_odds, away_odds, value_home, value_draw, value_away, expected_value, created_at)
		SELECT
			(SELECT id FROM prediction_runs WHERE name = '${namespace}_run' ORDER BY id DESC LIMIT 1),
			id,
			'1x2',
			0.52,
			0.24,
			0.24,
			2.10,
			3.40,
			3.10,
			0.09,
			-0.03,
			-0.02,
			0.09,
			NOW()
		FROM matches
		WHERE home_team LIKE '${namespace}_%';
	`);

	return seeded;
}
```

- [ ] **Step 3: Expand the predict test to the real flow**

Replace the spec body with:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';
import { ensureHybridPredictionData } from '../helpers/seed';

test('prediction result can be added to slip and placed as a ticket', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		await ensureHybridPredictionData(session);

		await page.goto('/predict');
		await expect(page.getByText(/results/i)).toBeVisible();
		await page.getByRole('button', { name: /^Add$/ }).first().click();
		await page.goto('/tickets');
		await page.getByLabel(/stake/i).fill('12');
		await page.getByRole('button', { name: /place ticket/i }).click();
		await expect(page.getByText(/active tickets/i)).toBeVisible();
	} finally {
		await cleanupSession(session);
	}
});
```

- [ ] **Step 4: Run the test to verify it fails on a concrete UI mismatch if any**

Run: `cd frontend && npx playwright test tests/e2e/hybrid/predict-slip-ticket.spec.ts --project=chromium-hybrid`
Expected: FAIL only if the rendered flow differs from the expected selectors/behavior.

- [ ] **Step 5: Refine the selectors and re-run**

Adjust button/text locators to the current predict page if needed. Then run:

Run: `cd frontend && npx playwright test tests/e2e/hybrid/predict-slip-ticket.spec.ts --project=chromium-hybrid`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/e2e/helpers/seed.ts frontend/tests/e2e/hybrid/predict-slip-ticket.spec.ts
git commit -m "test: cover predict to ticket e2e flow"
```

## Task 6: Add Hybrid Honesty Coverage for Live, Value Bets, Data, and Scrape Status

**Files:**
- Create: `frontend/tests/e2e/hybrid/live-value-data.spec.ts`
- Create: `frontend/tests/e2e/hybrid/scrape-job-honesty.spec.ts`
- Create or Modify: `frontend/tests/e2e/helpers/scrape.ts`
- Test: the two new hybrid specs

- [ ] **Step 1: Write the failing surface honesty test**

Create `frontend/tests/e2e/hybrid/live-value-data.spec.ts`:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';

test('live, value bets, and data pages show real-backend states without demo fallback', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		for (const route of ['/live', '/value-bets', '/data']) {
			await page.goto(route);
			await expect(page.locator('body')).not.toContainText(/Man City|Real Madrid|Juventus|PSG/);
		}
	} finally {
		await cleanupSession(session);
	}
});
```

Run: `cd frontend && npx playwright test tests/e2e/hybrid/live-value-data.spec.ts --project=chromium-hybrid`
Expected: FAIL if the UI still renders seeded demo data or if the page contract differs.

- [ ] **Step 2: Replace the brittle negative assertion with explicit honest-state assertions**

Update the spec to assert one of:

```ts
await expect(page.getByText(/unavailable|no .* available|failed to load/i)).toBeVisible();
```

or real seeded content:

```ts
await expect(page.locator('body')).toContainText(session.namespace);
```

Use page-specific logic rather than one shared fragile string rule.

- [ ] **Step 3: Add scrape helper for job orchestration**

Create `frontend/tests/e2e/helpers/scrape.ts`:

```ts
import { api, poll } from './backend';
import type { AuthSession } from './types';

export async function createAndExecuteScrapeJob(session: AuthSession): Promise<{ id: number; status: string }> {
	const create = await api<{ id: number }>(
		'/api/v1/data/scrape',
		{
			method: 'POST',
			body: JSON.stringify({
				job_type: 'scrape_odds',
				params: { future_days: 1 }
			})
		},
		session.token
	);

	if (create.status !== 201 || !create.json.id) {
		throw new Error(`Scrape job creation failed with status ${create.status}`);
	}

	await api(`/api/v1/data/scrape/${create.json.id}/execute`, { method: 'POST' }, session.token);

	const job = await poll(
		() => api<{ id: number; status: string }>(`/api/v1/data/scrape/${create.json.id}`, undefined, session.token),
		(result) => ['completed', 'failed', 'cancelled'].includes(result.json.status),
		30_000,
		1_000
	);

	return { id: create.json.id, status: job.json.status };
}
```

- [ ] **Step 4: Write the failing scrape honesty test**

Create `frontend/tests/e2e/hybrid/scrape-job-honesty.spec.ts`:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';
import { createAndExecuteScrapeJob } from '../helpers/scrape';

test('scrape page surfaces job status honestly', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		await createAndExecuteScrapeJob(session);
		await page.goto('/scrape');
		await expect(page.locator('body')).toContainText(/completed|failed|running/i);
	} finally {
		await cleanupSession(session);
	}
});
```

Run: `cd frontend && npx playwright test tests/e2e/hybrid/live-value-data.spec.ts tests/e2e/hybrid/scrape-job-honesty.spec.ts --project=chromium-hybrid`
Expected: FAIL only where page-state assertions need to be aligned to the actual UI.

- [ ] **Step 5: Align the assertions to the real routes and run until green**

Run: `cd frontend && npx playwright test tests/e2e/hybrid/live-value-data.spec.ts tests/e2e/hybrid/scrape-job-honesty.spec.ts --project=chromium-hybrid`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/e2e/helpers/scrape.ts frontend/tests/e2e/hybrid/live-value-data.spec.ts frontend/tests/e2e/hybrid/scrape-job-honesty.spec.ts
git commit -m "test: add hybrid honesty coverage for scrape and data surfaces"
```

## Task 7: Add the Opt-In Live Scrape -> Predict -> Ticket Suite

**Files:**
- Create: `frontend/tests/e2e/live/live-scrape-predict-ticket.spec.ts`
- Modify: `frontend/tests/e2e/helpers/scrape.ts`
- Test: `frontend/tests/e2e/live/live-scrape-predict-ticket.spec.ts`

- [ ] **Step 1: Write the failing live suite test**

Create `frontend/tests/e2e/live/live-scrape-predict-ticket.spec.ts`:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';
import { runLiveScrapeFlow } from '../helpers/scrape';

test('@live full live scrape to ticket flow works', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		await runLiveScrapeFlow(session);
		await page.goto('/data');
		await expect(page.locator('body')).not.toContainText(/unavailable|failed to load/i);
	} finally {
		await cleanupSession(session);
	}
});
```

Run: `cd frontend && E2E_MODE=live npx playwright test tests/e2e/live/live-scrape-predict-ticket.spec.ts --project=chromium-live`
Expected: FAIL with missing helper.

- [ ] **Step 2: Add the live scrape orchestrator**

Extend `frontend/tests/e2e/helpers/scrape.ts`:

```ts
import { getE2EConfig } from './backend';
import type { AuthSession } from './types';

export async function runLiveScrapeFlow(session: AuthSession): Promise<void> {
	const { liveScrapeTimeoutMs } = getE2EConfig();
	const job = await createAndExecuteScrapeJob(session);

	if (job.status !== 'completed') {
		throw new Error(`Live scrape flow failed with terminal status ${job.status}`);
	}

	const matches = await poll(
		() => api<Array<{ id: number }>>('/api/v1/matches?status=scheduled', undefined, session.token),
		(result) => Array.isArray(result.json) && result.json.length > 0,
		liveScrapeTimeoutMs,
		2_000
	);

	if (!Array.isArray(matches.json) || matches.json.length === 0) {
		throw new Error('No scheduled matches became available after live scrape');
	}
}
```

- [ ] **Step 3: Expand the live spec to the full browser path**

Replace the spec body with:

```ts
import { expect, test } from '@playwright/test';
import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSession } from '../helpers/cleanup';
import { runLiveScrapeFlow } from '../helpers/scrape';

test('@live full live scrape to ticket flow works', async ({ context, page }) => {
	const session = await createAuthenticatedSession(context);
	try {
		await runLiveScrapeFlow(session);

		await page.goto('/data');
		await expect(page.locator('body')).not.toContainText(/unavailable|failed to load/i);

		await page.goto('/predict');
		await expect(page.locator('body')).toContainText(/predict|results/i);

		await page.getByRole('button', { name: /^Add$/ }).first().click();
		await page.goto('/tickets');
		await page.getByLabel(/stake/i).fill('10');
		await page.getByRole('button', { name: /place ticket/i }).click();
		await expect(page.locator('body')).toContainText(/active tickets/i);
	} finally {
		await cleanupSession(session);
	}
});
```

- [ ] **Step 4: Run the live suite and observe the real-chain failure mode**

Run: `cd frontend && E2E_MODE=live npx playwright test tests/e2e/live/live-scrape-predict-ticket.spec.ts --project=chromium-live`
Expected: either PASS if the live chain is healthy, or FAIL with a concrete scrape/bridge/upstream error. Do not paper over that failure.

- [ ] **Step 5: Refine timeouts and assertions, not fallback logic**

If the live chain works but needs longer polling, adjust:

```ts
await runLiveScrapeFlow(session); // same helper, higher timeout via env or config
```

If the chain fails due to scraper/runtime issues, keep the failure explicit.

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/e2e/helpers/scrape.ts frontend/tests/e2e/live/live-scrape-predict-ticket.spec.ts
git commit -m "test: add opt-in live scrape to ticket suite"
```

## Task 8: Verify the Full Hybrid Suite and Document the Run Contract

**Files:**
- Optionally Create: `frontend/tests/e2e/README.md`
- Test: full hybrid suite and live suite listing

- [ ] **Step 1: Write a minimal E2E README if the run contract is not obvious**

Create `frontend/tests/e2e/README.md`:

```md
# Frontend E2E

- `npm run test:e2e` runs the stable hybrid suite against a real backend.
- `npm run test:e2e:live` runs the opt-in live scrape suite.
- Required env:
  - `E2E_BACKEND_URL`
  - optional `E2E_FRONTEND_URL`
- Backend must already be running.
```

- [ ] **Step 2: Run the full hybrid suite**

Run: `cd frontend && npm run test:e2e`
Expected: PASS

- [ ] **Step 3: Run live suite listing without forcing the full live chain**

Run: `cd frontend && E2E_MODE=live npx playwright test --list --project=chromium-live`
Expected: PASS, live suite is discoverable.

- [ ] **Step 4: Run frontend static verification**

Run: `cd frontend && npm run check`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/e2e/README.md frontend/tests/e2e frontend/playwright.config.ts frontend/package.json
git commit -m "test: finalize frontend real-backend e2e suites"
```

## Self-Review

- Spec coverage:
  - hybrid suite: covered in Tasks 1-6 and 8
  - live suite: covered in Task 7
  - real backend auth/bankroll/ticket flows: covered in Tasks 2-5
  - scrape honesty and honest unavailable states: covered in Task 6
- Placeholder scan:
  - no `TODO`, `TBD`, or “implement later” placeholders remain
  - commands and file paths are explicit
- Type consistency:
  - helper types are introduced in Task 2 and extended in Task 3
  - auth session, seeding, scrape helpers, and specs reuse the same names throughout
