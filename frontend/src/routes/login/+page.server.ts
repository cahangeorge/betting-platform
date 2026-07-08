import type { PageServerLoad, Actions } from './$types';
import { redirect, fail } from '@sveltejs/kit';

type CookieHeaderSource = Headers & {
	getSetCookie?: () => string[];
};

function getSetCookieHeaders(headers: Headers): string[] {
	const cookieHeaders = headers as CookieHeaderSource;
	if (typeof cookieHeaders.getSetCookie === 'function') {
		return cookieHeaders.getSetCookie();
	}

	const combinedHeader = headers.get('set-cookie');
	if (!combinedHeader) {
		return [];
	}

	return combinedHeader.split(/,(?=[^;,\s]+=[^;]+)/g);
}

function propagateAuthCookies(
	cookies: Parameters<Actions['login']>[0]['cookies'],
	headers: Headers
): boolean {
	let propagated = false;

	for (const cookieHeader of getSetCookieHeaders(headers)) {
		const segments = cookieHeader.split(';').map((segment) => segment.trim());
		const [nameValue, ...attributes] = segments;
		const separatorIndex = nameValue.indexOf('=');
		if (separatorIndex <= 0) {
			continue;
		}

		const name = nameValue.slice(0, separatorIndex);
		if (name !== 'access_token' && name !== 'refresh_token') {
			continue;
		}

		const value = nameValue.slice(separatorIndex + 1);
		const maxAge = attributes
			.map((attribute) => attribute.match(/^Max-Age=(\d+)$/i))
			.find(Boolean);
		const sameSite = attributes
			.map((attribute) => attribute.match(/^SameSite=(lax|strict|none)$/i))
			.find(Boolean)?.[1]
			?.toLowerCase() as 'lax' | 'strict' | 'none' | undefined;
		const secure = attributes.some((attribute) => attribute.toLowerCase() === 'secure');

		cookies.set(name, value, {
			path: '/',
			httpOnly: true,
			sameSite: sameSite ?? 'lax',
			secure,
			maxAge: maxAge ? Number(maxAge[1]) : name === 'access_token' ? 1800 : 604800
		});
		propagated = true;
	}

	return propagated;
}

export const load: PageServerLoad = async ({ cookies, url }) => {
	const token = cookies.get('access_token');
	if (token) {
		try {
			const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
			const meRes = await fetch(`${apiBase}/api/v1/auth/me`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (meRes.ok) {
				redirect(302, '/');
			}
		} catch {
			// not authenticated, show login
		}
	}
	return {};
};

export const actions: Actions = {
	login: async ({ cookies, request }) => {
		const formData = await request.formData();
		const email = formData.get('email') as string;
		const password = formData.get('password') as string;

		if (!email || !password) {
			return fail(400, { error: 'Email and password are required', email });
		}

		try {
			const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
			const res = await fetch(`${apiBase}/api/v1/auth/login`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, password })
			});

			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Login failed' }));
				return fail(res.status, { error: err.detail || 'Login failed', email });
			}

			const data = await res.json();

			const propagatedAuthCookies = propagateAuthCookies(cookies, res.headers);

			// Fall back to the JSON response body if the runtime did not expose Set-Cookie headers.
			if (!propagatedAuthCookies && data.access_token) {
				cookies.set('access_token', data.access_token, {
					path: '/',
					httpOnly: true,
					sameSite: 'lax',
					maxAge: 1800
				});
			}
		} catch (err) {
			return fail(502, { error: 'Backend unreachable. Is the API server running?', email });
		}

		redirect(302, '/');
	}
};
