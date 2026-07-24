import type { Cookies } from '@sveltejs/kit';
import type { User } from '../types.ts';

type CookieHeaderSource = Headers & {
	getSetCookie?: () => string[];
};

function getSetCookieHeaders(headers: Headers): string[] {
	const cookieHeaders = headers as CookieHeaderSource;
	if (typeof cookieHeaders.getSetCookie === 'function') return cookieHeaders.getSetCookie();

	const combinedHeader = headers.get('set-cookie');
	if (!combinedHeader) return [];

	return combinedHeader.split(/,(?=[^;,\s]+=[^;]+)/g);
}

export function propagateAuthCookies(cookies: Cookies, headers: Headers): boolean {
	let propagated = false;

	for (const cookieHeader of getSetCookieHeaders(headers)) {
		const segments = cookieHeader.split(';').map((segment) => segment.trim());
		const [nameValue, ...attributes] = segments;
		const separatorIndex = nameValue.indexOf('=');
		if (separatorIndex <= 0) continue;

		const name = nameValue.slice(0, separatorIndex);
		if (name !== 'access_token' && name !== 'refresh_token') continue;

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

export async function resolveRequestUser(
	cookies: Cookies,
	fetchImpl: typeof fetch,
	apiBase = process.env.BET_API_URL || 'http://localhost:8001'
): Promise<User | null> {
	try {
		const accessToken = cookies.get('access_token');
		if (accessToken) {
			const meResponse = await fetchImpl(`${apiBase}/api/v1/auth/me`, {
				headers: { Authorization: `Bearer ${accessToken}` }
			});
			if (meResponse.ok) return (await meResponse.json()) as User;
			if (meResponse.status !== 401) return null;
		}

		const refreshToken = cookies.get('refresh_token');
		if (!refreshToken) return null;

		const refreshResponse = await fetchImpl(`${apiBase}/api/v1/auth/refresh`, {
			method: 'POST',
			headers: { Cookie: `refresh_token=${refreshToken}` }
		});
		if (refreshResponse.ok) {
			propagateAuthCookies(cookies, refreshResponse.headers);
			return (await refreshResponse.json()) as User;
		}
		if (refreshResponse.status === 401) {
			cookies.delete('access_token', { path: '/' });
			cookies.delete('refresh_token', { path: '/' });
		}
	} catch {
		// A transient backend failure must not destroy otherwise valid cookies.
	}

	return null;
}
