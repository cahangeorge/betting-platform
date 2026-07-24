import type { PageServerLoad, Actions } from './$types';
import { redirect, fail } from '@sveltejs/kit';
import { createNoIndexPageMetaTags } from '../../lib/seo/site.ts';
import { propagateAuthCookies } from '$lib/server/auth-cookies';

export const load: PageServerLoad = async ({ cookies, url }) => {
	const token = cookies.get('access_token');
	let authenticated = false;

	if (token) {
		try {
			const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
			const meRes = await fetch(`${apiBase}/api/v1/auth/me`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (meRes.ok) {
				authenticated = true;
			}
		} catch {
			// not authenticated, show login
		}
	}

	if (authenticated) {
		redirect(302, '/');
	}

	return createNoIndexPageMetaTags(url, {
		title: 'Autentificare',
		description: 'Autentifică-te pentru a accesa spațiul privat de analiză Betfront.'
	});
};

export const actions: Actions = {
	login: async ({ cookies, request }) => {
		const formData = await request.formData();
		const email = formData.get('email') as string;
		const password = formData.get('password') as string;

		if (!email || !password) {
			return fail(400, { error: 'Emailul și parola sunt obligatorii.', email });
		}

		try {
			const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
			const res = await fetch(`${apiBase}/api/v1/auth/login`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, password })
			});

			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Autentificarea a eșuat.' }));
				return fail(res.status, { error: err.detail || 'Autentificarea a eșuat.', email });
			}

			const propagatedAuthCookies = propagateAuthCookies(cookies, res.headers);
			if (!propagatedAuthCookies) {
				return fail(502, {
					error: 'Autentificarea a reușit, dar sesiunea securizată nu a putut fi inițializată. Reîncearcă.',
					email
				});
			}
		} catch (err) {
			return fail(502, { error: 'Serviciul de autentificare nu este disponibil. Reîncearcă.', email });
		}

		redirect(302, '/');
	}
};
