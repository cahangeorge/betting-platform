import test from 'node:test';
import assert from 'node:assert/strict';

import { load } from '../../src/routes/+layout.server.ts';
import { resolveRequestUser } from '../../src/lib/server/auth-cookies.ts';

type CookieWrite = {
	name: string;
	value?: string;
	options?: { path?: string };
	operation: 'set' | 'delete';
};

function makeEvent(
	pathname: string,
	options: {
		accessToken?: string;
		refreshToken?: string;
		fetch?: typeof fetch;
		user?: App.Locals['user'];
	} = {}
) {
	const writes: CookieWrite[] = [];
	const values = new Map<string, string>();
	if (options.accessToken) values.set('access_token', options.accessToken);
	if (options.refreshToken) values.set('refresh_token', options.refreshToken);

	return {
			event: {
			url: new URL(`http://localhost${pathname}`),
			route: { id: pathname === '/' ? '/' : pathname },
			fetch: options.fetch ?? (async () => new Response(null, { status: 500 })),
			locals: { user: options.user ?? null },
			cookies: {
				get(name: string) {
					return values.get(name);
				},
				set(name: string, value: string, cookieOptions: { path?: string }) {
					values.set(name, value);
					writes.push({ name, value, options: cookieOptions, operation: 'set' });
				},
				delete(name: string, cookieOptions: { path?: string }) {
					values.delete(name);
					writes.push({ name, options: cookieOptions, operation: 'delete' });
				}
			}
		} as Parameters<typeof load>[0],
		writes
	};
}

test('protected routes redirect to /login without an access token', async () => {
	await assert.rejects(
		async () => {
			await load(makeEvent('/tickets').event);
		},
		(error: unknown) => {
			assert.equal((error as { status?: number }).status, 302);
			assert.equal((error as { location?: string }).location, '/login');
			return true;
		}
	);
});

test('root path redirects guests to the public product page', async () => {
	await assert.rejects(
		async () => {
			await load(makeEvent('/').event);
		},
		(error: unknown) => {
			assert.equal((error as { status?: number }).status, 302);
			assert.equal((error as { location?: string }).location, '/about');
			return true;
		}
	);
});

test('SSR restores an authenticated session with the refresh cookie', async () => {
	const requests: Array<{ url: string; init?: RequestInit }> = [];
	const fetchMock = (async (input: string | URL | Request, init?: RequestInit) => {
		requests.push({ url: String(input), init });
		const headers = new Headers();
		headers.append(
			'set-cookie',
			'access_token=new-access; Path=/; HttpOnly; SameSite=Lax; Max-Age=1800'
		);
		headers.append(
			'set-cookie',
			'refresh_token=new-refresh; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800'
		);
		return Response.json({ id: 7, email: 'qa@example.com' }, { headers });
	}) as typeof fetch;
	const { event, writes } = makeEvent('/tickets', {
		refreshToken: 'old-refresh',
		fetch: fetchMock
	});

	event.locals.user = await resolveRequestUser(event.cookies, event.fetch);
	const result = await load(event);

	assert.deepEqual(result, { user: { id: 7, email: 'qa@example.com' } });
	assert.equal(requests.length, 1);
	assert.match(requests[0].url, /\/api\/v1\/auth\/refresh$/);
	assert.equal(new Headers(requests[0].init?.headers).get('cookie'), 'refresh_token=old-refresh');
	assert.deepEqual(
		writes.filter((write) => write.operation === 'set').map((write) => [write.name, write.value]),
		[
			['access_token', 'new-access'],
			['refresh_token', 'new-refresh']
		]
	);
});

test('SSR clears rejected refresh cookies before redirecting', async () => {
	const fetchMock = (async () => Response.json({ detail: 'Invalid token' }, { status: 401 })) as typeof fetch;
	const { event, writes } = makeEvent('/tickets', {
		accessToken: 'expired-access',
		refreshToken: 'expired-refresh',
		fetch: fetchMock
	});
	event.locals.user = await resolveRequestUser(event.cookies, event.fetch);

	await assert.rejects(
		async () => load(event),
		(error: unknown) => {
			assert.equal((error as { status?: number }).status, 302);
			assert.equal((error as { location?: string }).location, '/login');
			return true;
		}
	);

	assert.deepEqual(
		writes.filter((write) => write.operation === 'delete').map((write) => write.name),
		['access_token', 'refresh_token']
	);
});
