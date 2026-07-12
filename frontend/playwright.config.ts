import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

import { defineConfig } from '@playwright/test';

const mode = process.env.E2E_MODE === 'live' ? 'live' : 'hybrid';
const frontendURL = process.env.E2E_FRONTEND_URL ?? 'http://127.0.0.1:5175';
const backendURL = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8001';
const backendTarget = new URL(backendURL);
const backendHost = backendTarget.hostname;
const backendPort = backendTarget.port || (backendTarget.protocol === 'https:' ? '443' : '80');
const backendHealthURL = new URL('/api/v1/health', backendURL).toString();
const backendCwd = process.env.E2E_BACKEND_CWD ?? '../backend';
const backendCwdAbsolute = resolve(process.cwd(), backendCwd);
const defaultBackendPythonCommand = existsSync(resolve(backendCwdAbsolute, '.venv/bin/python'))
	? '.venv/bin/python'
	: 'python';
const backendPythonCommand = process.env.E2E_BACKEND_PYTHON_COMMAND ?? defaultBackendPythonCommand;
const backendAlembicCommand =
	process.env.E2E_BACKEND_ALEMBIC_COMMAND ??
	(existsSync(resolve(backendCwdAbsolute, '.venv/bin/alembic'))
		? '.venv/bin/alembic'
		: `${backendPythonCommand} -m alembic`);
const backendDatabaseURL = process.env.BET_DATABASE_URL ?? '';
const runBackendMigrations =
	process.env.E2E_BACKEND_RUN_MIGRATIONS === '1' ||
	(backendDatabaseURL.length > 0 && !backendDatabaseURL.startsWith('sqlite+'));
const backendCommand =
	process.env.E2E_BACKEND_COMMAND ??
	`${runBackendMigrations ? `${backendAlembicCommand} upgrade head && ` : ''}${backendPythonCommand} -m uvicorn app.main:app --host ${backendHost} --port ${backendPort}`;
const isLiveMode = mode === 'live';
const skipWebServer = process.env.E2E_SKIP_WEBSERVER === '1';
const frontendTarget = new URL(frontendURL);
const frontendHost = frontendTarget.hostname;
const frontendPort = frontendTarget.port || (frontendTarget.protocol === 'https:' ? '443' : '80');

export default defineConfig({
	testDir: './tests/e2e',
	outputDir: '../.playwright-artifacts/frontend/test-results',
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	workers: 1,
	retries: isLiveMode ? 0 : 1,
	timeout: isLiveMode ? 180_000 : 90_000,
	expect: {
		timeout: 10_000
	},
	use: {
		baseURL: frontendURL,
		screenshot: 'only-on-failure',
		trace: 'retain-on-failure',
		video: 'off'
	},
	...(skipWebServer
		? {}
		: {
				webServer: [
					{
						command: backendCommand,
						cwd: backendCwd,
						url: backendHealthURL,
						name: 'backend',
						timeout: 120_000,
						reuseExistingServer: !process.env.CI,
						env: {
							...process.env
						}
					},
					{
						command: `pnpm exec svelte-kit sync && pnpm exec vite dev --host ${frontendHost} --port ${frontendPort} --strictPort`,
						url: frontendURL,
						name: 'frontend',
						timeout: 120_000,
						reuseExistingServer: !process.env.CI,
						env: {
							...process.env,
							E2E_MODE: mode,
							E2E_FRONTEND_URL: frontendURL,
							E2E_BACKEND_URL: backendURL,
							BET_API_URL: backendURL,
							PUBLIC_API_URL: backendURL
						}
					}
				]
			}),
	reporter: [['list']],
	projects: [
		{
			name: 'chromium-hybrid',
			testMatch: /hybrid\/.*\.spec\.(t|j)s$/,
			use: {
				browserName: 'chromium'
			}
		},
		{
			name: 'chromium-live',
			testMatch: /live\/.*\.spec\.(t|j)s$/,
			grep: /@live/,
			use: {
				browserName: 'chromium'
			}
		}
	]
});
