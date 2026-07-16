import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const monitoring = readFileSync(new URL('../../src/routes/monitoring/+page.svelte', import.meta.url), 'utf8');
const analytics = readFileSync(new URL('../../src/lib/api/analytics.ts', import.meta.url), 'utf8');

test('monitoring presents CLV with explicit coverage instead of zero-filled evidence', () => {
	assert.match(analytics, /\/api\/v1\/analytics\/clv/);
	assert.match(monitoring, /Closing line value/);
	assert.match(monitoring, /Coverage/);
	assert.match(monitoring, /average_market_best_clv_pct/);
});
