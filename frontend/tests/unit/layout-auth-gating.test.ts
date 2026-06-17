import test from 'node:test';
import assert from 'node:assert/strict';

import { load } from '../../src/routes/+layout.server.ts';

function makeEvent(pathname: string, accessToken?: string) {
	return {
		url: new URL(`http://localhost${pathname}`),
		cookies: {
			get(name: string) {
				return name === 'access_token' ? accessToken : undefined;
			}
		}
	} as Parameters<typeof load>[0];
}

test('protected routes redirect to /login without an access token', async () => {
	await assert.rejects(
		async () => {
			await load(makeEvent('/tickets'));
		},
		(error: unknown) => {
			assert.equal((error as { status?: number }).status, 302);
			assert.equal((error as { location?: string }).location, '/login');
			return true;
		}
	);
});

test('root path redirects guests to /board before auth lookup', async () => {
	await assert.rejects(
		async () => {
			await load(makeEvent('/'));
		},
		(error: unknown) => {
			assert.equal((error as { status?: number }).status, 302);
			assert.equal((error as { location?: string }).location, '/board');
			return true;
		}
	);
});
