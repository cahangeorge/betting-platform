import test from 'node:test';
import assert from 'node:assert/strict';

import { artifactSummary } from '../../src/lib/job-runs.helpers.ts';
import type { ScheduledJobRun } from '../../src/lib/types.ts';

function makeRun(artifacts: Record<string, unknown> | null): ScheduledJobRun {
	return {
		id: 1,
		job_id: 1,
		scheduled_job_id: 1,
		scrape_job_id: null,
		task_type: 'soccerdata_ingestion',
		status: 'completed',
		detail: null,
		artifacts,
		taskiq_task_id: null,
		attempt: 1,
		queued_at: null,
		started_at: null,
		finished_at: null,
		duration_ms: null,
		error: null,
		triggered_by: 'test',
		due_at: null,
		created_at: null
	};
}

test('summarizes the soccerdata generation and penaltyblog model handoff artifacts', () => {
	assert.equal(
		artifactSummary(
			makeRun({
				provider_dataset_generation_ids: [41],
				model_artifact_ids: [73]
			})
		),
		'provider dataset generation: 41 · model artifact: 73'
	);
});

test('does not advertise scalar handoff metadata as a completed artifact list', () => {
	assert.equal(artifactSummary(makeRun({ source_generation_id: 41 })), 'No artifacts yet');
});
