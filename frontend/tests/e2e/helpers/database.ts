import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';

import { test } from '@playwright/test';

const execFileAsync = promisify(execFile);

const SQLITE_SKIP_REASON =
	'Direct e2e database fixtures require Postgres; local sqlite-backed hybrid runs skip these seeded fixture checks.';

const PYTHON_SQL_RUNNER = String.raw`
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    index = 0
    while index < len(sql):
        char = sql[index]
        current.append(char)
        if char == "'":
            if in_single_quote and index + 1 < len(sql) and sql[index + 1] == "'":
                current.append(sql[index + 1])
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif char == ';' and not in_single_quote:
            statement = ''.join(current).strip().rstrip(';').strip()
            if statement:
                statements.append(statement)
            current = []
        index += 1

    statement = ''.join(current).strip().rstrip(';').strip()
    if statement:
        statements.append(statement)
    return statements


async def main() -> None:
    database_url = os.environ['BET_DATABASE_URL']
    sql = os.environ['E2E_SQL']
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            outputs: list[str] = []
            for statement in split_sql(sql):
                # Fixture SQL is already complete SQL and may contain JSON
                # object keys such as "schema_version": 1. Passing it
                # through sqlalchemy.text() misreads those colons as bind
                # parameters, so execute it at the driver boundary instead.
                result = await connection.exec_driver_sql(statement)
                if result.returns_rows:
                    rows = result.fetchall()
                    outputs.extend('|'.join('' if value is None else str(value) for value in row) for row in rows)
            if outputs:
                print('\n'.join(outputs))
    finally:
        await engine.dispose()


asyncio.run(main())
`;

function stripEnvValue(value: string): string {
	const trimmed = value.trim();
	const quote = trimmed[0];
	if ((quote === '"' || quote === "'") && trimmed.endsWith(quote)) {
		return trimmed.slice(1, -1);
	}
	return trimmed;
}

function backendCwd(): string {
	return resolve(process.cwd(), process.env.E2E_BACKEND_CWD ?? '../backend');
}

function readBackendEnvDatabaseUrl(): string | null {
	try {
		const envPath = resolve(backendCwd(), '.env');
		const content = readFileSync(envPath, 'utf8');
		for (const line of content.split(/\r?\n/)) {
			const match = line.match(/^\s*BET_DATABASE_URL\s*=\s*(.+?)\s*$/);
			if (match) return stripEnvValue(match[1]);
		}
	} catch {
		// Missing backend .env is fine in CI where BET_DATABASE_URL is provided directly.
	}
	return null;
}

export function getBackendDatabaseUrlForE2E(): string {
	return process.env.BET_DATABASE_URL ?? readBackendEnvDatabaseUrl() ?? '';
}

export function usesSqliteBackendDatabase(): boolean {
	const databaseUrl = getBackendDatabaseUrlForE2E().toLowerCase();
	return databaseUrl.startsWith('sqlite') || databaseUrl.includes('+aiosqlite:');
}

export function directDatabaseFixturesAvailable(): boolean {
	if (process.env.E2E_DISABLE_DIRECT_DB_FIXTURES === '1') return false;
	if (process.env.E2E_FORCE_DIRECT_DB_FIXTURES === '1') return true;
	return !usesSqliteBackendDatabase();
}

export function skipIfDirectDatabaseFixturesUnavailable(): void {
	test.skip(!directDatabaseFixturesAvailable(), SQLITE_SKIP_REASON);
}

export function shouldSkipDirectDatabaseCleanup(): boolean {
	return !directDatabaseFixturesAvailable();
}

function defaultPythonCommand(): string {
	const venvPython = resolve(backendCwd(), '.venv/bin/python');
	return existsSync(venvPython) ? venvPython : 'python';
}

export async function runDirectSql(sql: string): Promise<string> {
	const databaseUrl = getBackendDatabaseUrlForE2E();
	if (!databaseUrl) {
		throw new Error('BET_DATABASE_URL is required for direct e2e database fixtures.');
	}

	const pythonCommand = process.env.E2E_BACKEND_PYTHON_COMMAND ?? defaultPythonCommand();
	const { stdout } = await execFileAsync(pythonCommand, ['-c', PYTHON_SQL_RUNNER], {
		cwd: backendCwd(),
		env: {
			...process.env,
			BET_DATABASE_URL: databaseUrl,
			E2E_SQL: sql
		},
		maxBuffer: 1024 * 1024 * 4
	});

	return stdout.trim();
}
