import { expect, test } from '@playwright/test';

const frontendURL = process.env.E2E_FRONTEND_URL ?? 'http://127.0.0.1:5175';

test('public SEO resources are crawlable without authentication', async ({ request }) => {
	const robots = await request.get('/robots.txt');
	expect(robots.status()).toBe(200);
	expect(robots.headers()['content-type']).toContain('text/plain');
	expect(await robots.text()).toContain(`Sitemap: ${frontendURL}/sitemap.xml`);

	const sitemap = await request.get('/sitemap.xml');
	expect(sitemap.status()).toBe(200);
	expect(sitemap.headers()['content-type']).toContain('application/xml');
	const sitemapXml = await sitemap.text();
	expect(sitemapXml).toContain(`<loc>${frontendURL}/about</loc>`);
	expect(sitemapXml).toContain(`<loc>${frontendURL}/methodology</loc>`);
	expect(sitemapXml).toContain(`<loc>${frontendURL}/responsible-gambling</loc>`);
	expect(sitemapXml).not.toContain('/login');
	expect(sitemapXml).not.toContain('/signup');
});

test('public marketing pages are server-rendered and cacheable for anonymous visitors', async ({ request }) => {
	for (const [pathname, heading] of [
		['/about', 'Un flux mai clar pentru analiza pariurilor sportive'],
		['/methodology', 'De la date la o decizie revizuibilă'],
		['/responsible-gambling', 'Analiza nu elimină riscul']
	] as const) {
		const response = await request.get(pathname);
		expect(response.status()).toBe(200);
		expect(response.headers()['cache-control']).toContain('public');
		const html = await response.text();
		expect(html).toContain('<html lang="ro">');
		expect(html).toContain(heading);
	}
});

test('anonymous root enters through the public product page', async ({ request }) => {
	const response = await request.get('/', { maxRedirects: 0 });
	expect(response.status()).toBe(302);
	expect(response.headers().location).toBe('/about');
});

test('legal drafts are public, noindex, and signup enforces acknowledgement server-side', async ({ request }) => {
	for (const [pathname, heading] of [
		['/terms', 'Termeni de utilizare'],
		['/privacy', 'Notă de confidențialitate']
	] as const) {
		const response = await request.get(pathname);
		expect(response.status()).toBe(200);
		const html = await response.text();
		expect(html).toContain(heading);
		expect(html).toContain('name="robots" content="noindex,follow"');
		expect(html).toContain('Necesită');
	}

	const rejectedSignup = await request.post('/signup', {
		form: {
			name: 'Audit User',
			email: 'audit@example.com',
			password: 'password123',
			confirmPassword: 'password123'
		}
	});
	// Direct action requests serialize the failure payload with HTTP 200; the embedded action status is 400.
	expect(rejectedSignup.status()).toBe(200);
	expect(await rejectedSignup.text()).toContain('Trebuie să confirmi vârsta legală aplicabilă');
});

test('auth pages stay private and unknown routes return a real 404', async ({ request }) => {
	const login = await request.get('/login');
	expect(login.status()).toBe(200);
	expect(login.headers()['cache-control']).toContain('private');
	expect(login.headers()['cache-control']).toContain('no-store');

	const missing = await request.get('/not-a-real-betfront-route', { maxRedirects: 0 });
	expect(missing.status()).toBe(404);
});

test('brand assets are raster images with stable public URLs', async ({ request }) => {
	for (const pathname of ['/favicon.png', '/apple-touch-icon.png', '/social/betfront-platform.png']) {
		const response = await request.get(pathname);
		expect(response.status()).toBe(200);
		expect(response.headers()['content-type']).toBe('image/png');
	}
});

test('public and legal pages do not overflow mobile viewports', async ({ page }) => {
	for (const width of [320, 390]) {
		await page.setViewportSize({ width, height: 844 });
		for (const path of ['/about', '/login', '/signup', '/terms', '/privacy']) {
			await page.goto(path);
			const geometry = await page.evaluate(() => ({
				clientWidth: document.documentElement.clientWidth,
				scrollWidth: document.documentElement.scrollWidth
			}));
			expect(geometry.scrollWidth, `${path} at ${width}px`).toBeLessThanOrEqual(
				geometry.clientWidth
			);
		}
	}
});
