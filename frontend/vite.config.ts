import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		watch: {
			ignored: ['**/test-results/**', '**/playwright-report/**', '**/.playwright-artifacts/**']
		},
		proxy: {
			'/api': {
				target: 'http://localhost:8001',
				changeOrigin: true,
				ws: true
			}
		}
	}
});
