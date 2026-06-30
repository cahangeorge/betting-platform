import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const autoRegisterServiceWorker = process.env.npm_lifecycle_event !== 'dev';
const localTrustedOrigins = [
	'http://127.0.0.1:5174',
	'http://127.0.0.1:5175',
	'http://127.0.0.1:8080',
	'http://127.0.0.1:8081',
	'http://localhost:5174',
	'http://localhost:5175',
	'http://localhost:8080',
	'http://localhost:8081'
];

const envTrustedOrigins = (process.env.CSRF_TRUSTED_ORIGINS ?? '')
	.split(',')
	.map((origin) => origin.trim())
	.filter(Boolean);

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter(),
		csrf: {
			trustedOrigins: [...new Set([...localTrustedOrigins, ...envTrustedOrigins])]
		},
		serviceWorker: {
			register: autoRegisterServiceWorker
		},
		version: {
			pollInterval: 300000
		}
	}
};

export default config;
