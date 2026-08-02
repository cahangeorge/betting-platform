import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const api = readFileSync(new URL('../../src/lib/api/provider-runtime.ts', import.meta.url), 'utf8');
const types = readFileSync(new URL('../../src/lib/types.ts', import.meta.url), 'utf8');
const monitoringPage = readFileSync(new URL('../../src/routes/monitoring/+page.svelte', import.meta.url), 'utf8');
const runTable = readFileSync(
	new URL('../../src/lib/components/jobs/ScheduledJobRunTable.svelte', import.meta.url),
	'utf8'
);

test('provider runtime client uses the source-scoped, provider-safe snapshot endpoint', () => {
	const providerRuntimeTypes = types.slice(
		types.indexOf('// ─── Provider runtime observability'),
		types.indexOf('// ─── Polling')
	);

	assert.match(api, /\/api\/v1\/provider\/runtime/);
	assert.match(providerRuntimeTypes, /interface ProviderRuntimeSnapshot/);
	assert.match(providerRuntimeTypes, /interface ProviderLaneSnapshot/);
	assert.match(providerRuntimeTypes, /interface ProviderPipelinePhase/);
	assert.match(providerRuntimeTypes, /interface ProviderRuntimeAlert/);
	assert.match(providerRuntimeTypes, /phases: ProviderPipelinePhase\[\]/);
	assert.match(providerRuntimeTypes, /cache_state/);
	assert.match(providerRuntimeTypes, /failed: number/);
	assert.doesNotMatch(providerRuntimeTypes, /api_key|access_token|authorization/i);
	assert.doesNotMatch(runTable, /title=\{run\.detail \|\| run\.error/);
});

test('provider runtime monitoring is requested and rendered only for administrators', () => {
	assert.match(monitoringPage, /const isAdmin = \$derived\(Boolean\(\$page\.data\.user\?\.is_admin\)\)/);
	assert.match(monitoringPage, /if \(!isAdmin\) \{[\s\S]*await loadJobs\(\);/);
	assert.match(monitoringPage, /\{#if isAdmin\}[\s\S]*data-testid="provider-runtime-panel"/);
	assert.match(monitoringPage, /state === 'unknown' \? 'neutral'/);
});
