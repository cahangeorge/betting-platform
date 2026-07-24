import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('service worker deduplicates precache assets and never caches API or navigation responses', async () => {
	const source = await readFile('src/service-worker.ts', 'utf8');

	assert.match(source, /Array\.from\(new Set\(\[\.\.\.build, \.\.\.files, OFFLINE_FALLBACK\]\)\)/);
	assert.match(source, /if \(isApiCall\) \{\s*event\.respondWith\(fetch\(event\.request\)\)/);
	assert.doesNotMatch(source, /cache\.put\(request/);
	const navigationPolicy = source.slice(source.indexOf('async function navigationFallback'));
	assert.doesNotMatch(navigationPolicy, /cache\.match\(request\)/);
	assert.match(source, /else if \(isAsset\)/);
});

test('service worker only removes its own versioned caches during activation', async () => {
	const source = await readFile('src/service-worker.ts', 'utf8');

	assert.match(source, /const CACHE_PREFIX = 'betfront-';/);
	assert.match(
		source,
		/keys\s*\.filter\(\(key\) => key\.startsWith\(CACHE_PREFIX\) && key !== CACHE\)/
	);
});

test('PWA manifest supplies raster any and maskable icons at install sizes', async () => {
	const manifest = JSON.parse(await readFile('static/manifest.json', 'utf8')) as {
		icons: Array<{ src: string; sizes: string; type: string; purpose: string }>;
	};

	for (const size of ['192x192', '512x512']) {
		assert.ok(
			manifest.icons.some(
				(icon) =>
					icon.src === `/icons/icon-${size.split('x')[0]}.png` &&
					icon.sizes === size &&
					icon.type === 'image/png' &&
					icon.purpose === 'any'
			)
		);
		assert.ok(
			manifest.icons.some(
				(icon) =>
					icon.src === `/icons/icon-${size.split('x')[0]}-maskable.png` &&
					icon.sizes === size &&
					icon.type === 'image/png' &&
					icon.purpose === 'maskable'
			)
		);
	}
});

test('service worker updates require an explicit confirmation before activation reloads the page', async () => {
	const source = await readFile('src/lib/components/PWAUpdateBanner.svelte', 'utf8');
	const betslip = await readFile('src/lib/stores/betslip.ts', 'utf8');

	assert.match(source, /const confirmed = window\.confirm\(/);
	assert.match(source, /if \(!confirmed\) \{\s*return;/);
	assert.match(source, /let reloadAfterActivation = false;/);
	assert.match(source, /if \(!reloadAfterActivation\) \{\s*return;/);
	assert.match(source, /betslipHasUnsavedDraft/);
	assert.match(betslip, /function storageKeyForUser\(userId: number\)/);
	assert.match(betslip, /sessionStorage\.setItem\(storageKey, JSON\.stringify\(state\)\)/);
	assert.match(betslip, /sessionStorage\.getItem\(storageKeyForUser\(userId\)\)/);
});

test('offline fallback only offers an online retry and does not loop back to the dashboard', async () => {
	const offline = await readFile('static/offline.html', 'utf8');

	assert.match(offline, /window\.location\.reload\(\)/);
	assert.doesNotMatch(offline, /href="\/"/);
});
