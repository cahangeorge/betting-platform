import { defineConfig } from '@playwright/test';

const frontendURL = process.env.E2E_PWA_FRONTEND_URL ?? 'https://127.0.0.1:4173';

export default defineConfig({
	testDir: './tests/e2e/pwa',
	outputDir: '../.playwright-artifacts/frontend/pwa-test-results',
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 120_000,
	expect: {
		timeout: 15_000
	},
	use: {
		baseURL: frontendURL,
		browserName: 'chromium',
		ignoreHTTPSErrors: true,
		launchOptions: {
			args: ['--ignore-certificate-errors']
		},
		actionTimeout: 15_000,
		screenshot: 'only-on-failure',
		trace: 'retain-on-failure',
		video: 'off'
	},
	webServer: {
		command: 'pnpm build && node tests/e2e/pwa/https-preview.mjs',
		url: frontendURL,
		ignoreHTTPSErrors: true,
		timeout: 240_000,
		reuseExistingServer: false,
		env: {
			...process.env,
			BET_TRADING_PAPER_ENABLED: 'false'
		}
	},
	reporter: [['list']],
	projects: [
		{
			name: 'chromium-pwa-production'
		}
	]
});
