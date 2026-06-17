import type { BrowserContext } from '@playwright/test';

import { backendRequest, getE2EEnv, poll, waitForBackendReady, withBearerToken } from './backend';
import type { AuthSession, AuthTokenResponse, AuthUser, Bankroll, TestCredentials } from './types';

function makeCredentials(): TestCredentials {
	const namespace = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
	return {
		email: `e2e-${namespace}@example.com`,
		name: `E2E ${namespace}`,
		password: `Passw0rd!-${namespace}`
	};
}

async function setAuthCookies(context: BrowserContext, accessToken: string): Promise<void> {
	const { frontendURL } = getE2EEnv();

	await context.addCookies([
		{
			name: 'access_token',
			value: accessToken,
			url: frontendURL,
			httpOnly: true,
			sameSite: 'Lax',
			secure: frontendURL.startsWith('https://')
		}
	]);
}

async function createBankroll(token: string): Promise<Bankroll> {
	return await backendRequest<Bankroll>('/api/v1/bankroll', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			...withBearerToken(token)
		},
		body: JSON.stringify({
			name: `E2E Bankroll ${Date.now()}`,
			type: 'paper',
			initial_balance: 1000,
			currency: 'EUR'
		})
 	});
}

export async function createAuthenticatedSession(context: BrowserContext): Promise<AuthSession> {
	await waitForBackendReady();

	const credentials = makeCredentials();
	const token = await backendRequest<AuthTokenResponse>('/api/v1/auth/signup', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(credentials)
	});

	const user = await poll(
		async () =>
			await backendRequest<AuthUser>('/api/v1/auth/me', {
				headers: withBearerToken(token.access_token)
			}),
		(value) => value.id > 0,
		10_000,
		250
	);

	const bankroll = await createBankroll(token.access_token);
	await setAuthCookies(context, token.access_token);

	return {
		namespace: credentials.email.replace(/^e2e-/, '').replace(/@example\.com$/, ''),
		credentials,
		user,
		token,
		bankroll
	};
}
