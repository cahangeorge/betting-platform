import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('Prepare is the canonical data-preparation workspace', async () => {
	const source = await readFile('src/routes/prepare/+page.svelte', 'utf8');
	assert.match(source, /id="selection"/);
	assert.match(source, /id="coverage"/);
	assert.match(source, /id="controls"/);
	assert.doesNotMatch(source, /href="\/scrape/);
});

test('legacy scrape route preserves search and hash while redirecting', async () => {
	const source = await readFile('src/routes/scrape/+page.svelte', 'utf8');
	const redirect = await readFile('src/lib/components/LegacyRouteRedirect.svelte', 'utf8');
	assert.match(source, /target="\/prepare"/);
	assert.match(redirect, /window\.location\.search/);
	assert.match(redirect, /window\.location\.hash/);
});
