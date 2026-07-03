import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

const backendProxyTarget =
	process.env.E2E_BACKEND_URL ?? process.env.BET_API_URL ?? 'http://localhost:8001';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		watch: {
			ignored: ['**/test-results/**', '**/playwright-report/**', '**/.playwright-artifacts/**']
		},
		proxy: {
			'/api': {
				target: backendProxyTarget,
				changeOrigin: true,
				ws: true
			}
		}
	}
});
