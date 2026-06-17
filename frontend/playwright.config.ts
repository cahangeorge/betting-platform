import { defineConfig } from '@playwright/test';

const mode = process.env.E2E_MODE === 'live' ? 'live' : 'hybrid';
const frontendURL = process.env.E2E_FRONTEND_URL ?? 'http://127.0.0.1:5175';
const backendURL = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8001';
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
				webServer: {
					command: `pnpm exec svelte-kit sync && pnpm exec vite dev --host ${frontendHost} --port ${frontendPort} --strictPort`,
					url: frontendURL,
					timeout: 120_000,
					reuseExistingServer: !process.env.CI,
					env: {
						...process.env,
						E2E_MODE: mode,
						E2E_FRONTEND_URL: frontendURL,
						E2E_BACKEND_URL: backendURL
					}
				}
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
