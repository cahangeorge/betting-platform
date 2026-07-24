import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('../../src/lib/api/model-governance.ts', import.meta.url), 'utf8');
const panel = readFileSync(new URL('../../src/lib/components/ModelGovernancePanel.svelte', import.meta.url), 'utf8');

test('model governance client exposes the persisted evidence surfaces', () => {
	assert.match(source, /model-governance\/evaluations/);
	assert.match(source, /model-governance\/certifications/);
	assert.match(source, /model-governance\/monitoring/);
	assert.match(source, /model-governance\/evidence/);
});

test('model governance evidence is latest-request-only and reports selection failures', () => {
	assert.match(panel, /const evidenceRequests = createRequestGeneration\(\)/);
	assert.match(panel, /if \(!evidenceRequests\.isCurrent\(requestId\)\) return/);
	assert.match(panel, /evidenceError = caught instanceof Error/);
	assert.match(panel, /role="alert"/);
	assert.match(panel, /<h1 id="model-governance-title"/);
});
