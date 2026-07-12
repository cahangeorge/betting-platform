import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const preparePagePath = path.resolve('src/routes/prepare/+page.svelte');

test('Prepare workflow cards use valid, keyboard-accessible scrape workspace links', async () => {
	const source = await readFile(preparePagePath, 'utf8');

	assert.match(source, /href: '\/scrape#selection'/);
	assert.match(source, /href: '\/scrape#coverage'/);
	assert.match(source, /href: '\/scrape#controls'/);
	assert.match(source, /href=\{step\.href\}/);
	assert.match(source, /class="group block min-h-56/);
	assert.match(source, /href="\/scrape"/);
	assert.doesNotMatch(source, /<a href="\/scrape"><Button>/);
});
