import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const autoRegisterServiceWorker = process.env.npm_lifecycle_event !== 'dev';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter(),
		csrf: {
			trustedOrigins: []
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
