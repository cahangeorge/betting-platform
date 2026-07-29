import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('Prepare is the canonical data-preparation workspace', async () => {
	const source = await readFile('src/routes/prepare/+page.svelte', 'utf8');
	assert.match(source, /id="selection"/);
	assert.match(source, /id="coverage"/);
	assert.match(source, /id="controls"/);
	assert.match(source, /Top 5 Europa/);
	assert.match(source, /Răsfoiește catalogul complet/);
	assert.match(source, /Setări avansate de rulare/);
	assert.match(source, /filteredCountries\.slice\(0, 12\)/);
	assert.match(source, /selectedCountries\.length > 0 \|\| leagueQuery\.trim\(\)/);
	assert.match(source, /let futureDays = \$state\('1'\)/);
	assert.match(source, /futureIntervalDays >= 1 && futureIntervalDays <= 31/);
	assert.match(source, /Intl\.DateTimeFormat\(\)\.resolvedOptions\(\)\.timeZone \|\| 'UTC'/);
	assert.match(source, /timezone: browserTimezone/);
	assert.match(source, /label="Zi țintă peste \(zile\)"/);
	assert.match(source, /max="31"/);
	assert.match(source, /Pentru mai multe zile, pornește câte o colectare separată/);
	assert.doesNotMatch(source, /Orizont personalizat mai lung/);
	assert.doesNotMatch(source, /href="\/scrape/);
});

test('legacy routes issue permanent redirects without running old data loaders', async () => {
	const source = await readFile('src/routes/scrape/+page.svelte', 'utf8');
	const redirect = await readFile('src/lib/navigation/legacy-redirect.ts', 'utf8');
	const scrapeLoad = await readFile('src/routes/scrape/+page.server.ts', 'utf8');
	const liveLoad = await readFile('src/routes/live/+page.server.ts', 'utf8');
	const valueLoad = await readFile('src/routes/value-bets/+page.server.ts', 'utf8');
	assert.match(source, /target="\/prepare"/);
	assert.match(redirect, /redirect\(308/);
	assert.match(redirect, /url\.searchParams/);
	assert.match(scrapeLoad, /'\/prepare'/);
	assert.match(liveLoad, /view: 'live'/);
	assert.match(valueLoad, /view: 'value'/);
	assert.match(scrapeLoad, /PageServerLoad/);
	assert.match(liveLoad, /PageServerLoad/);
	assert.match(valueLoad, /PageServerLoad/);
});
