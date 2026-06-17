import type { PageServerLoad, Actions } from './$types';
import { redirect, fail } from '@sveltejs/kit';

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

			// Set cookies from the response
			const setCookieHeaders = res.headers.getSetCookie();
			for (const cookie of setCookieHeaders) {
				const [name, ...rest] = cookie.split(';')[0].split('=');
				if (name === 'access_token' || name === 'refresh_token') {
					cookies.set(name, rest.join('='), {
						path: '/',
						httpOnly: true,
						sameSite: 'lax',
						maxAge: name === 'access_token' ? 1800 : 604800
					});
				}
			}

			// Also set token from JSON response body
			if (data.access_token) {
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