import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { defineConfig } from '@playwright/test';

const mode = process.env.E2E_MODE === 'live' ? 'live' : 'hybrid';
const frontendURL = process.env.E2E_FRONTEND_URL ?? 'http://127.0.0.1:5175';
const backendURL = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8001';
const backendTarget = new URL(backendURL);
const backendHost = backendTarget.hostname;
const backendPort = backendTarget.port || (backendTarget.protocol === 'https:' ? '443' : '80');
const backendReadyURL = new URL('/ready', backendURL).toString();
const backendCwd = process.env.E2E_BACKEND_CWD ?? '../backend';
const backendCwdAbsolute = resolve(process.cwd(), backendCwd);

function readBackendEnvValue(name: string): string {
	const envPath = resolve(backendCwdAbsolute, '.env');
	if (!existsSync(envPath)) return '';
	const prefix = `${name}=`;
	const line = readFileSync(envPath, 'utf8')
		.split(/\r?\n/)
		.find((entry) => entry.trimStart().startsWith(prefix));
	if (!line) return '';
	const value = line.trimStart().slice(prefix.length).trim();
	const quote = value[0];
	return (quote === '"' || quote === "'") && value.endsWith(quote)
		? value.slice(1, -1)
		: value;
}

const defaultBackendPythonCommand = existsSync(resolve(backendCwdAbsolute, '.venv/bin/python'))
	? '.venv/bin/python'
	: 'python';
const backendPythonCommand = process.env.E2E_BACKEND_PYTHON_COMMAND ?? defaultBackendPythonCommand;
const backendAlembicCommand =
	process.env.E2E_BACKEND_ALEMBIC_COMMAND ??
	(existsSync(resolve(backendCwdAbsolute, '.venv/bin/alembic'))
		? '.venv/bin/alembic'
		: `${backendPythonCommand} -m alembic`);
const backendDatabaseURL =
	process.env.BET_DATABASE_URL?.trim() || readBackendEnvValue('BET_DATABASE_URL');
const runBackendMigrations =
	process.env.E2E_BACKEND_RUN_MIGRATIONS === '1' ||
	(backendDatabaseURL.length > 0 && !backendDatabaseURL.startsWith('sqlite'));
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
	retries: 0,
	timeout: isLiveMode ? 180_000 : 90_000,
	expect: {
		timeout: 10_000
	},
	use: {
		baseURL: frontendURL,
		actionTimeout: 15_000,
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
						url: backendReadyURL,
						name: 'backend',
						timeout: 120_000,
						reuseExistingServer: !process.env.CI,
						env: {
							...process.env,
							...(backendDatabaseURL ? { BET_DATABASE_URL: backendDatabaseURL } : {})
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
		},
		{
			name: 'firefox-hybrid-smoke',
			testMatch: /hybrid\/cross-browser-smoke\.spec\.(t|j)s$/,
			use: {
				browserName: 'firefox'
			}
		},
		{
			name: 'webkit-hybrid-smoke',
			testMatch: /hybrid\/cross-browser-smoke\.spec\.(t|j)s$/,
			use: {
				browserName: 'webkit'
			}
		}
	]
});
