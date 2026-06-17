import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { deleteSeededMatches } from './seed';
import type { AuthSession } from './types';

const execFileAsync = promisify(execFile);

const DEFAULT_POSTGRES_CONTAINER = process.env.E2E_POSTGRES_CONTAINER ?? 'bet_postgres_1';
const DEFAULT_DB_NAME = process.env.E2E_POSTGRES_DB ?? 'betting_platform';
const DEFAULT_DB_USER = process.env.E2E_POSTGRES_USER ?? 'betuser';
const DEFAULT_CONTAINER_RUNTIME = process.env.E2E_CONTAINER_RUNTIME ?? 'podman';

function sqlLiteral(value: string): string {
	return `'${value.split("'").join("''")}'`;
}

async function runSql(sql: string): Promise<void> {
	await execFileAsync(
		DEFAULT_CONTAINER_RUNTIME,
		[
			'exec',
			'-i',
			DEFAULT_POSTGRES_CONTAINER,
			'psql',
			'-U',
			DEFAULT_DB_USER,
			'-d',
			DEFAULT_DB_NAME,
			'-t',
			'-A',
			'-c',
			sql
		],
		{
			maxBuffer: 1024 * 1024 * 4
		}
	);
}

export async function cleanupSessionArtifacts(session: AuthSession): Promise<void> {
	const competition = `E2E ${session.namespace}`;

	await deleteSeededMatches(competition);

	await runSql(`
		DELETE FROM scrape_jobs
		WHERE job_type LIKE ${sqlLiteral(`e2e-%${session.namespace}%`)}
			OR CAST(params AS TEXT) LIKE ${sqlLiteral(`%${session.namespace}%`)};
		DELETE FROM prediction_runs WHERE user_id = ${session.user.id};
		DELETE FROM tickets WHERE user_id = ${session.user.id};
		DELETE FROM bankrolls WHERE user_id = ${session.user.id};
		DELETE FROM sessions WHERE user_id = ${session.user.id};
		DELETE FROM users WHERE id = ${session.user.id} OR email = ${sqlLiteral(session.credentials.email)};
	`);
}

export async function cleanupScrapeJobs(jobTypePrefix: string): Promise<void> {
	await runSql(`
		DELETE FROM scrape_jobs
		WHERE job_type LIKE ${sqlLiteral(`${jobTypePrefix}%`)};
	`);
}
