import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('SEO head is centralized and app.html does not ship duplicate static metadata', async () => {
	const appHtml = await readFile('src/app.html', 'utf8');
	const seoHead = await readFile('src/lib/components/SeoHead.svelte', 'utf8');
	const layoutLoad = await readFile('src/routes/+layout.ts', 'utf8');

	assert.match(appHtml, /<html lang="ro">/);
	assert.doesNotMatch(appHtml, /<title>/);
	assert.doesNotMatch(appHtml, /name="description"/);
	assert.match(seoHead, /MetaTags/);
	assert.match(seoHead, /JsonLd/);
	assert.match(seoHead, /deepMerge/);
	assert.match(layoutLoad, /createBaseMetaTags\(url\)/);
});

test('SEO defaults are noindex and only explicit marketing routes opt into indexing', async () => {
	const site = await readFile('src/lib/seo/site.ts', 'utf8');
	const layoutServer = await readFile('src/routes/+layout.server.ts', 'utf8');

	assert.match(site, /robots: 'noindex,follow'/);
	assert.match(site, /robots: 'index,follow'/);
	assert.match(site, /INDEXABLE_PAGE_PATHS = \['\/about', '\/methodology', '\/responsible-gambling'\]/);
	assert.match(layoutServer, /isPublicPagePath\(url\.pathname\)/);
	assert.match(layoutServer, /route\?\.id === null|route\.id === null/);
	assert.doesNotMatch(layoutServer, /startsWith/);
});

test('authenticated auth-page redirects happen outside backend request try blocks', async () => {
	const login = await readFile('src/routes/login/+page.server.ts', 'utf8');
	const signup = await readFile('src/routes/signup/+page.server.ts', 'utf8');

	for (const source of [login, signup]) {
		assert.match(source, /let authenticated = false/);
		assert.match(source, /if \(authenticated\) \{\s*redirect\(302, '\/'\);\s*\}/s);
	}
});

test('anonymous root uses the public product entry and legal pages stay public but noindex', async () => {
	const layoutServer = await readFile('src/routes/+layout.server.ts', 'utf8');
	const publicRoutes = await readFile('src/lib/seo/public-routes.ts', 'utf8');
	const terms = await readFile('src/routes/terms/+page.ts', 'utf8');
	const privacy = await readFile('src/routes/privacy/+page.ts', 'utf8');

	assert.match(layoutServer, /!user && url\.pathname === '\/'/);
	assert.match(layoutServer, /redirect\(302, '\/about'\)/);
	assert.match(publicRoutes, /'\/terms'/);
	assert.match(publicRoutes, /'\/privacy'/);
	assert.match(terms, /createNoIndexPageMetaTags/);
	assert.match(privacy, /createNoIndexPageMetaTags/);
});

test('signup requires legal-age acknowledgement before the backend request', async () => {
	const action = await readFile('src/routes/signup/+page.server.ts', 'utf8');
	const form = await readFile('src/lib/components/AuthForm.svelte', 'utf8');

	assert.match(action, /legalAccepted.*=== 'accepted'/);
	assert.match(action, /errors\.legalAccepted/);
	assert.ok(action.indexOf('Object.keys(errors)') < action.indexOf('/api/v1/auth/signup'));
	assert.match(form, /name="legalAccepted"/);
	assert.match(form, /href="\/terms"/);
	assert.match(form, /href="\/privacy"/);
});
