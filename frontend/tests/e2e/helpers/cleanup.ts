import { runDirectSql, shouldSkipDirectDatabaseCleanup } from './database';
import { deleteSeededMatches } from './seed';
import type { AuthSession } from './types';

function sqlLiteral(value: string): string {
	return `'${value.split("'").join("''")}'`;
}

async function runSql(sql: string): Promise<void> {
	if (shouldSkipDirectDatabaseCleanup()) return;
	await runDirectSql(sql);
}


export async function cleanupSessionArtifacts(session: AuthSession): Promise<void> {
	const competition = `E2E ${session.namespace}`;

	if (shouldSkipDirectDatabaseCleanup()) return;

	await deleteSeededMatches(competition);

	await runSql(`
		DELETE FROM scheduled_jobs
		WHERE config ->> '_created_by_user_id' = ${sqlLiteral(String(session.user.id))}
			OR name LIKE ${sqlLiteral(`%${session.namespace}%`)};
		DELETE FROM scrape_jobs
		WHERE job_type LIKE ${sqlLiteral(`e2e-%${session.namespace}%`)}
			OR CAST(params AS TEXT) LIKE ${sqlLiteral(`%${session.namespace}%`)};
		DELETE FROM settlements
		WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id})
			OR bet_placement_id IN (
				SELECT id FROM bet_placements
				WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id})
			);
		DELETE FROM ledger_entries
		WHERE bankroll_id IN (SELECT id FROM bankrolls WHERE user_id = ${session.user.id})
			OR ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
		DELETE FROM bet_placements
		WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
		DELETE FROM tickets WHERE user_id = ${session.user.id};
		DELETE FROM ticket_batches
		WHERE bankroll_id IN (SELECT id FROM bankrolls WHERE user_id = ${session.user.id});
		DELETE FROM prediction_runs WHERE user_id = ${session.user.id};
		DELETE FROM strategies
		WHERE name LIKE ${sqlLiteral(`%${session.namespace}%`)};
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
