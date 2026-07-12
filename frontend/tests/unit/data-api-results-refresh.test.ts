import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('data API queues a scoped final-results refresh job', async () => {
	const source = await readFile('src/lib/api/data.ts', 'utf8');

	assert.match(source, /refreshFinalResults\(matchIds: number\[\]\)/);
	assert.match(source, /match_ids: matchIds/);
	assert.match(source, /\/api\/v1\/data\/scrape\/results-refresh/);
});
