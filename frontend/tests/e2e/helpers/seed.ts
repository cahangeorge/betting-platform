import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { backendRequest, withBearerToken } from './backend';
import type { AuthSession, SeededHybridFixtures } from './types';

const execFileAsync = promisify(execFile);

const DEFAULT_POSTGRES_CONTAINER = process.env.E2E_POSTGRES_CONTAINER ?? 'bet_postgres_1';
const DEFAULT_DB_NAME = process.env.E2E_POSTGRES_DB ?? 'betting_platform';
const DEFAULT_DB_USER = process.env.E2E_POSTGRES_USER ?? 'betuser';
const DEFAULT_CONTAINER_RUNTIME = process.env.E2E_CONTAINER_RUNTIME ?? 'podman';

function sqlLiteral(value: string): string {
	return `'${value.split("'").join("''")}'`;
}

async function runSql(sql: string): Promise<string> {
	const { stdout } = await execFileAsync(
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

	return stdout.trim();
}

async function tableHasColumn(tableName: string, columnName: string): Promise<boolean> {
	const output = await runSql(`
		SELECT EXISTS (
			SELECT 1
			FROM information_schema.columns
			WHERE table_name = ${sqlLiteral(tableName)}
				AND column_name = ${sqlLiteral(columnName)}
		);
	`);

	return output.split('\n')[0]?.trim() === 't';
}

async function insertMatch(input: {
	externalId: string;
	competition: string;
	homeTeam: string;
	awayTeam: string;
	status: 'scheduled' | 'live';
	matchDateExpression: string;
	homeScore?: number;
	awayScore?: number;
}): Promise<number> {
	const sql = `
		INSERT INTO matches (external_id, sport, home_team, away_team, home_score, away_score, status, match_date, competition, season)
		VALUES (
			${sqlLiteral(input.externalId)},
			'football',
			${sqlLiteral(input.homeTeam)},
			${sqlLiteral(input.awayTeam)},
			${input.homeScore ?? 'NULL'},
			${input.awayScore ?? 'NULL'},
			${sqlLiteral(input.status)},
			${input.matchDateExpression},
			${sqlLiteral(input.competition)},
			'2026'
		)
		RETURNING id;
	`;

	return Number((await runSql(sql)).split('\n')[0]?.trim());
}

async function insertOdds(matchId: number, input: { homeOdds: number; drawOdds: number; awayOdds: number; market?: string }) {
	await runSql(`
		INSERT INTO odds_entries (match_id, bookmaker, market, home_odds, draw_odds, away_odds, timestamp)
		VALUES (
			${matchId},
			'Betfair',
			${sqlLiteral(input.market ?? '1x2')},
			${input.homeOdds},
			${input.drawOdds},
			${input.awayOdds},
			NOW()
		);
	`);
}

async function insertLiveStats(matchId: number) {
	await runSql(`
		INSERT INTO match_stats (
			match_id,
			source,
			home_xg,
			away_xg,
			possession_home,
			possession_away,
			shots_home,
			shots_away
		)
		VALUES (
			${matchId},
			'e2e',
			1.42,
			0.66,
			61,
			39,
			11,
			5
		);
	`);
}

async function insertPredictionRun(session: AuthSession, matchIds: number[]): Promise<number> {
	const sql = `
		INSERT INTO prediction_runs (
			user_id,
			name,
			model_type,
			ensemble,
			status,
			matches_count,
			started_at,
			completed_at
		)
		VALUES (
			${session.user.id},
			${sqlLiteral(`E2E ${session.namespace}`)},
			'PoissonGoalsModel',
			FALSE,
			'completed',
			${matchIds.length},
			NOW(),
			NOW()
		)
		RETURNING id;
	`;

	return Number((await runSql(sql)).split('\n')[0]?.trim());
}

async function insertModelPrediction(input: {
	runId: number;
	matchId: number;
	modelType?: string;
	market: string;
	homeProb: number;
	drawProb: number;
	awayProb: number;
	homeOdds?: number;
	drawOdds?: number;
	awayOdds?: number;
}) {
	const hasModelType = await tableHasColumn('model_predictions', 'model_type');
	const columns = [
		'run_id',
		...(hasModelType ? ['model_type'] : []),
		'match_id',
		'market',
		'home_prob',
		'draw_prob',
		'away_prob',
		'home_odds',
		'draw_odds',
		'away_odds',
		'value_home',
		'value_draw',
		'value_away',
		'expected_value'
	];
	const values = [
		String(input.runId),
		...(hasModelType ? [sqlLiteral(input.modelType ?? 'PoissonGoalsModel')] : []),
		String(input.matchId),
		sqlLiteral(input.market),
		String(input.homeProb),
		String(input.drawProb),
		String(input.awayProb),
		String(input.homeOdds ?? 'NULL'),
		String(input.drawOdds ?? 'NULL'),
		String(input.awayOdds ?? 'NULL'),
		'0.09',
		'0.02',
		'-0.04',
		'0.11'
	];

	await runSql(`
		INSERT INTO model_predictions (${columns.join(', ')})
		VALUES (${values.join(', ')});
	`);
}

export async function setBankrollBalance(bankrollId: number, balance: number): Promise<void> {
	await runSql(`
		UPDATE bankrolls
		SET balance = ${balance}
		WHERE id = ${bankrollId};
	`);
}

async function createTicketForMatch(session: AuthSession, matchId: number): Promise<number> {
	const ticket = await backendRequest<{ id: number }>('/api/v1/tickets', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			...withBearerToken(session.token.access_token)
		},
		body: JSON.stringify({
			ticket_type: 'single',
			stake: 12,
			bankroll_id: session.bankroll.id,
			legs: [
				{
					match_id: matchId,
					selection: 'home',
					market: '1x2',
					odds: 1.91,
					bookmaker: 'Betfair'
				}
			]
		})
	});

	return ticket.id;
}

export async function seedHybridFixtures(session: AuthSession): Promise<SeededHybridFixtures> {
	const competition = `E2E ${session.namespace}`;
	const scheduledHome = `Atlas ${session.namespace}`;
	const scheduledAway = `Comets ${session.namespace}`;
	const liveHome = `Rovers ${session.namespace}`;
	const liveAway = `United ${session.namespace}`;

	const scheduledMatchId = await insertMatch({
		externalId: `e2e-scheduled-${session.namespace}`,
		competition,
		homeTeam: scheduledHome,
		awayTeam: scheduledAway,
		status: 'scheduled',
		matchDateExpression: "NOW() + INTERVAL '2 hours'"
	});

	const liveMatchId = await insertMatch({
		externalId: `e2e-live-${session.namespace}`,
		competition,
		homeTeam: liveHome,
		awayTeam: liveAway,
		status: 'live',
		matchDateExpression: "NOW() - INTERVAL '35 minutes'",
		homeScore: 1,
		awayScore: 0
	});

	await insertOdds(scheduledMatchId, { homeOdds: 1.91, drawOdds: 3.4, awayOdds: 4.1 });
	await insertOdds(liveMatchId, { homeOdds: 1.65, drawOdds: 3.8, awayOdds: 5.0 });
	await insertLiveStats(liveMatchId);

	const predictionRunId = await insertPredictionRun(session, [scheduledMatchId, liveMatchId]);
	await insertModelPrediction({
		runId: predictionRunId,
		matchId: scheduledMatchId,
		market: '1x2',
		homeProb: 0.64,
		drawProb: 0.21,
		awayProb: 0.15,
		homeOdds: 1.91,
		drawOdds: 3.4,
		awayOdds: 4.1
	});
	await insertModelPrediction({
		runId: predictionRunId,
		matchId: liveMatchId,
		market: '1x2',
		homeProb: 0.68,
		drawProb: 0.19,
		awayProb: 0.13,
		homeOdds: 1.65,
		drawOdds: 3.8,
		awayOdds: 5.0
	});

	const seededTicketId = await createTicketForMatch(session, scheduledMatchId);

	return {
		competition,
		scheduledMatchId,
		scheduledMatchLabel: `${scheduledHome} vs ${scheduledAway}`,
		liveMatchId,
		liveMatchLabel: `${liveHome} vs ${liveAway}`,
		predictionRunId,
		seededTicketId
	};
}

export async function deleteSeededMatches(competition: string): Promise<void> {
	await runSql(`
		DELETE FROM match_stats
		WHERE match_id IN (SELECT id FROM matches WHERE competition = ${sqlLiteral(competition)});

		DELETE FROM odds_entries
		WHERE match_id IN (SELECT id FROM matches WHERE competition = ${sqlLiteral(competition)});

		DELETE FROM matches
		WHERE competition = ${sqlLiteral(competition)};
	`);
}
